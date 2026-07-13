import asyncio
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from src.calendar_api import (
    get_events,
    get_events_for_date,
    format_event,
    format_weekly_summary,
    format_daily_summary,
    is_user_authenticated,
    get_timezone,
    now_local,
    get_upcoming_birthdays,
)
from src.telegram_bot import create_bot, load_users, is_user_silenced

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60 * 15
REMINDER_HOURS = [8, 20]
DAILY_SUMMARY_HOUR = 7
WEEKLY_SUMMARY_HOUR = 20
WEEKLY_SUMMARY_DAY = 6

# Controle para não enviar notificações duplicadas
sent_notifications: set[str] = set()

# Estatísticas do bot
bot_stats = {
    "started_at": None,
    "last_notification": None,
    "notifications_sent": 0,
    "errors_count": 0,
}

# ID do admin para receber alertas de erro
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def notification_key(notification_type: str, user_id: str, hour: int) -> str:
    today = now_local().date().isoformat()
    return f"{notification_type}:{user_id}:{today}:{hour}"


def _key_date(key: str) -> str:
    parts = key.split(":")
    return parts[2] if len(parts) > 2 else ""


def cleanup_old_keys():
    # Remove chaves de dias anteriores (datas ISO comparam como string).
    today = now_local().date().isoformat()
    old_keys = {k for k in sent_notifications if _key_date(k) < today}
    sent_notifications.difference_update(old_keys)


async def send_message(bot, chat_id: str, text: str):
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    bot_stats["last_notification"] = now_local().isoformat()
    bot_stats["notifications_sent"] += 1


async def send_error_alert(bot, error_message: str):
    if not ADMIN_CHAT_ID:
        return
    try:
        text = f"🚨 *Erro no bot:*\n\n`{error_message[:500]}`"
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode="Markdown")
    except Exception:
        pass


async def check_reminders(app):
    current_hour = now_local().hour
    if current_hour not in REMINDER_HOURS:
        return

    users = load_users()
    bot = app.bot

    for telegram_id, user_data in users.items():
        user_id = user_data.get("name")
        if not user_id or not is_user_authenticated(user_id):
            continue
        if is_user_silenced(int(telegram_id)):
            continue

        key = notification_key("reminder", user_id, current_hour)
        if key in sent_notifications:
            continue

        try:
            today_events = get_events(user_id, days_ahead=1)
            if today_events:
                lines = [format_event(ev) for ev in today_events]
                text = "🔔 *Eventos de hoje*\n\n" + "\n".join(lines)
                await send_message(bot, telegram_id, text)

            tomorrow_events = get_events(user_id, days_ahead=2)
            tomorrow_only = [ev for ev in tomorrow_events if ev not in today_events]
            if tomorrow_only:
                lines = [format_event(ev) for ev in tomorrow_only]
                text = "🔔 *Eventos de amanhã*\n\n" + "\n".join(lines)
                await send_message(bot, telegram_id, text)

            sent_notifications.add(key)

        except Exception as e:
            logger.error(f"Erro ao verificar eventos de {user_id}: {e}")
            bot_stats["errors_count"] += 1
            await send_error_alert(app.bot, f"Erro lembretes ({user_id}): {e}")


async def check_daily_summary(app):
    current_hour = now_local().hour
    if current_hour != DAILY_SUMMARY_HOUR:
        return

    users = load_users()
    bot = app.bot

    for telegram_id, user_data in users.items():
        user_id = user_data.get("name")
        if not user_id or not is_user_authenticated(user_id):
            continue
        if is_user_silenced(int(telegram_id)):
            continue

        key = notification_key("daily", user_id, current_hour)
        if key in sent_notifications:
            continue

        try:
            text = format_daily_summary(user_id)
            await send_message(bot, telegram_id, text)
            sent_notifications.add(key)
        except Exception as e:
            logger.error(f"Erro ao enviar resumo diário para {user_id}: {e}")
            bot_stats["errors_count"] += 1
            await send_error_alert(app.bot, f"Erro resumo diário ({user_id}): {e}")


async def check_weekly_summary(app):
    now = now_local()
    if now.weekday() != WEEKLY_SUMMARY_DAY or now.hour != WEEKLY_SUMMARY_HOUR:
        return

    users = load_users()
    bot = app.bot

    for telegram_id, user_data in users.items():
        user_id = user_data.get("name")
        if not user_id or not is_user_authenticated(user_id):
            continue
        if is_user_silenced(int(telegram_id)):
            continue

        key = notification_key("weekly", user_id, now.hour)
        if key in sent_notifications:
            continue

        try:
            text = format_weekly_summary(user_id)
            await send_message(bot, telegram_id, text)

            birthdays = get_upcoming_birthdays(user_id, days_ahead=7)
            if birthdays:
                lines = ["🎂 *Aniversários da semana:*\n"]
                for bday in birthdays:
                    day_str = bday["date"].strftime("%d/%m")
                    lines.append(f"• {bday['name']} — {day_str}")
                await send_message(bot, telegram_id, "\n".join(lines))

            sent_notifications.add(key)

        except Exception as e:
            logger.error(f"Erro ao enviar resumo semanal para {user_id}: {e}")
            bot_stats["errors_count"] += 1
            await send_error_alert(app.bot, f"Erro resumo semanal ({user_id}): {e}")


async def check_couple_conflicts(app):
    """Verifica conflitos de horário entre os dois usuários."""
    current_hour = now_local().hour
    if current_hour != DAILY_SUMMARY_HOUR:
        return

    users = load_users()
    authenticated = [
        (tid, data["name"])
        for tid, data in users.items()
        if data.get("name") and is_user_authenticated(data["name"])
    ]

    if len(authenticated) < 2:
        return

    key = notification_key("conflicts", "couple", current_hour)
    if key in sent_notifications:
        return

    tz = get_timezone()
    today = now_local().date()

    # Verifica conflitos para os próximos 3 dias
    conflicts_found = []
    for offset in range(3):
        check_date = today + timedelta(days=offset)

        all_events = {}
        for tid, uid in authenticated:
            try:
                events = get_events_for_date(uid, check_date)
                all_events[uid] = events
            except Exception:
                continue

        if len(all_events) < 2:
            continue

        user_ids = list(all_events.keys())
        events_a = all_events[user_ids[0]]
        events_b = all_events[user_ids[1]]

        for ev_a in events_a:
            start_a = ev_a.get("start", {})
            end_a = ev_a.get("end", {})
            if "dateTime" not in start_a:
                continue

            a_start = datetime.fromisoformat(start_a["dateTime"]).astimezone(tz)
            a_end = datetime.fromisoformat(end_a["dateTime"]).astimezone(tz)

            for ev_b in events_b:
                start_b = ev_b.get("start", {})
                end_b = ev_b.get("end", {})
                if "dateTime" not in start_b:
                    continue

                b_start = datetime.fromisoformat(start_b["dateTime"]).astimezone(tz)
                b_end = datetime.fromisoformat(end_b["dateTime"]).astimezone(tz)

                if a_start < b_end and b_start < a_end:
                    day_str = check_date.strftime("%d/%m")
                    conflicts_found.append(
                        f"• {day_str}: {ev_a.get('summary', '?')} ({a_start.strftime('%H:%M')}) "
                        f"x {ev_b.get('summary', '?')} ({b_start.strftime('%H:%M')})"
                    )

    if conflicts_found:
        text = "⚠️ *Conflitos de agenda do casal:*\n\n" + "\n".join(conflicts_found)
        bot = app.bot
        for tid, uid in authenticated:
            if not is_user_silenced(int(tid)):
                try:
                    await send_message(bot, tid, text)
                except Exception:
                    pass

    sent_notifications.add(key)


async def notification_loop(app):
    logger.info("Loop de notificações iniciado")
    while True:
        try:
            cleanup_old_keys()
            await check_reminders(app)
            await check_daily_summary(app)
            await check_weekly_summary(app)
            await check_couple_conflicts(app)
        except Exception as e:
            logger.error(f"Erro no loop de notificações: {e}")
            bot_stats["errors_count"] += 1
            try:
                await send_error_alert(app.bot, f"Erro no loop: {e}")
            except Exception:
                pass
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN não configurado no .env")
        return

    bot_stats["started_at"] = now_local().isoformat()

    app = create_bot(token)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        logger.info("Bot do Telegram iniciado. Aguardando comandos...")

        notification_task = asyncio.create_task(notification_loop(app))

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Encerrando...")
        finally:
            notification_task.cancel()
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    loop.run_until_complete(run())


if __name__ == "__main__":
    main()
