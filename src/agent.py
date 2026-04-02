import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from src.calendar_api import (
    get_events,
    format_event,
    format_event_short,
    format_weekly_summary,
    format_daily_summary,
    get_upcoming_birthdays,
    is_user_authenticated,
    get_timezone,
)
from src.telegram_bot import create_bot, load_users, is_user_silenced

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60 * 15  # verifica a cada 15 minutos
REMINDER_HOURS = [8, 20]
DAILY_SUMMARY_HOUR = 7
WEEKLY_SUMMARY_HOUR = 20
WEEKLY_SUMMARY_DAY = 6  # domingo


async def send_message(bot, chat_id: str, text: str):
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")


async def check_reminders(app):
    """Lembretes de eventos de hoje e amanhã (8h e 20h)."""
    current_hour = datetime.now().hour
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

        except Exception as e:
            logger.error(f"Erro ao verificar eventos de {user_id}: {e}")


async def check_upcoming_events(app):
    """Lembrete de eventos que começam em ~30 minutos."""
    users = load_users()
    bot = app.bot
    tz = get_timezone()
    now = datetime.now(tz)

    for telegram_id, user_data in users.items():
        user_id = user_data.get("name")
        if not user_id or not is_user_authenticated(user_id):
            continue
        if is_user_silenced(int(telegram_id)):
            continue

        try:
            events = get_events(user_id, days_ahead=1)

            for ev in events:
                start = ev.get("start", {})
                if "dateTime" not in start:
                    continue

                event_start = datetime.fromisoformat(start["dateTime"]).astimezone(tz)
                diff = (event_start - now).total_seconds() / 60

                if 15 <= diff <= 30:
                    summary = ev.get("summary", "Sem título")
                    time_str = event_start.strftime("%H:%M")
                    text = f"⏰ *Lembrete:* {summary} começa às {time_str} (em ~{int(diff)} min)"
                    await send_message(bot, telegram_id, text)

        except Exception as e:
            logger.error(f"Erro ao verificar próximos eventos de {user_id}: {e}")


async def check_daily_summary(app):
    """Resumo diário enviado às 7h."""
    current_hour = datetime.now().hour
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

        try:
            text = format_daily_summary(user_id)
            await send_message(bot, telegram_id, text)
        except Exception as e:
            logger.error(f"Erro ao enviar resumo diário para {user_id}: {e}")


async def check_weekly_summary(app):
    """Resumo semanal enviado no domingo às 20h."""
    now = datetime.now()
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

        except Exception as e:
            logger.error(f"Erro ao enviar resumo semanal para {user_id}: {e}")


async def notification_loop(app):
    logger.info("Loop de notificações iniciado")
    while True:
        try:
            await check_upcoming_events(app)
            await check_reminders(app)
            await check_daily_summary(app)
            await check_weekly_summary(app)
        except Exception as e:
            logger.error(f"Erro no loop de notificações: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN não configurado no .env")
        return

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
