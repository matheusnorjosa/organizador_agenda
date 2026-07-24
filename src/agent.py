import asyncio
import json
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

# Agendas conjuntas do casal: compromissos comuns, nunca conflito entre os dois.
SHARED_COUPLE_CALENDARS = {"familia", "família"}

# Janela de busca para avisar sobre compromissos recém-criados
NEW_EVENT_LOOKAHEAD_DAYS = 30

# Depois de uma parada longa não vale recuperar tudo: evita despejar dias de
# eventos de uma vez quando o bot volta do zero.
MAX_RECOVERY_WINDOW = timedelta(hours=24)

# Estado que precisa sobreviver a reinício. Fica em volume próprio: o
# container é recriado a cada deploy e perderia o arquivo de outra forma.
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "estado")
STATE_PATH = os.path.join(STATE_DIR, "notificacoes.json")

# Eventos já anunciados como novos, para não repetir o aviso a cada ciclo
announced_new_events: set[str] = set()

# A partir de quando um evento conta como novo. Carregado do disco no primeiro
# ciclo, para que um deploy não crie janela cega nem enxurrada de avisos.
new_events_since: datetime | None = None

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


def _load_new_events_marker() -> datetime | None:
    """Lê do disco o instante da última verificação de eventos novos.

    Devolve None quando não há estado utilizável — nesse caso o bot trata
    como primeira execução e não anuncia o que já existia.
    """
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as state_file:
            saved = json.load(state_file).get("ultima_verificacao_eventos")
    except (OSError, ValueError):
        return None

    if not saved:
        return None

    try:
        marker = datetime.fromisoformat(saved)
    except ValueError:
        logger.warning(f"Marco de eventos novos inválido no estado: {saved!r}")
        return None

    if marker.tzinfo is None:
        # Sem fuso não dá para comparar com a data de criação dos eventos.
        logger.warning("Marco de eventos novos salvo sem fuso; ignorando.")
        return None

    return marker


def _save_new_events_marker(moment: datetime):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as state_file:
            json.dump({"ultima_verificacao_eventos": moment.isoformat()}, state_file)
    except OSError as e:
        # Perder o marco só custa uma janela cega no próximo reinício.
        logger.error(f"Não foi possível salvar o estado de notificações: {e}")


def _event_created_at(event: dict) -> datetime | None:
    """Momento em que o evento foi criado, como datetime com fuso."""
    created = event.get("created")
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_new_event(event: dict) -> str:
    creator = event.get("creator") or {}
    author = creator.get("displayName") or creator.get("email")
    text = f"🆕 *Novo compromisso na agenda*\n\n{format_event(event)}"
    if author:
        text += f"\n\nAdicionado por {author}"
    return text


async def check_new_events(app):
    """Avisa quando um compromisso novo aparece na agenda.

    Os lembretes de horário fixo não cobrem o que é criado no meio do dia:
    um evento marcado às 9h para as 19h não gerava aviso nenhum.
    """
    global new_events_since

    cycle_started_at = now_local()

    if new_events_since is None:
        new_events_since = _load_new_events_marker()

        if new_events_since is None:
            # Primeira execução: o que já existe não é novidade.
            new_events_since = cycle_started_at
            _save_new_events_marker(cycle_started_at)
            return

        # Recupera o que apareceu enquanto o bot esteve fora do ar, mas sem
        # despejar o acumulado de dias depois de uma parada longa.
        oldest_allowed = cycle_started_at - MAX_RECOVERY_WINDOW
        if new_events_since < oldest_allowed:
            new_events_since = oldest_allowed

    users = load_users()
    bot = app.bot
    fetch_failed = False

    for telegram_id, user_data in users.items():
        user_id = user_data.get("name")
        if not user_id or not is_user_authenticated(user_id):
            continue
        if is_user_silenced(int(telegram_id)):
            continue

        try:
            events = get_events(user_id, days_ahead=NEW_EVENT_LOOKAHEAD_DAYS)
        except Exception as e:
            logger.error(f"Erro ao buscar eventos novos de {user_id}: {e}")
            bot_stats["errors_count"] += 1
            fetch_failed = True
            continue

        for event in events:
            created_at = _event_created_at(event)
            if created_at is None or created_at <= new_events_since:
                continue

            key = f"new:{user_id}:{event.get('id', '')}"
            if key in announced_new_events:
                continue
            announced_new_events.add(key)

            try:
                await send_message(bot, telegram_id, _format_new_event(event))
            except Exception as e:
                logger.error(f"Erro ao avisar evento novo para {user_id}: {e}")
                bot_stats["errors_count"] += 1

    # Só avança o marco se a rodada foi completa. Com falha de busca, os
    # eventos daquele usuário seriam pulados para sempre.
    if not fetch_failed:
        new_events_since = cycle_started_at
        _save_new_events_marker(cycle_started_at)


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


def _is_shared_couple_event(event: dict) -> bool:
    """Evento de agenda conjunta do casal (ex: Família)."""
    calendar_name = event.get("_calendar_name") or ""
    return calendar_name.strip().lower() in SHARED_COUPLE_CALENDARS


def _timed_events(events: list[dict], tz) -> list[tuple[dict, datetime, datetime]]:
    """Eventos com hora marcada, já convertidos para o fuso local.

    Descarta eventos de agenda conjunta: são compromissos comuns do casal,
    não disputa de horário entre os dois.
    """
    timed = []
    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})
        if "dateTime" not in start or "dateTime" not in end:
            continue
        if _is_shared_couple_event(event):
            continue
        timed.append((
            event,
            datetime.fromisoformat(start["dateTime"]).astimezone(tz),
            datetime.fromisoformat(end["dateTime"]).astimezone(tz),
        ))
    return timed


def _event_identity(event: dict, start: datetime, end: datetime) -> tuple:
    """Chave que identifica a mesma ocorrência vista em agendas diferentes."""
    return ((event.get("summary") or "").strip().lower(), start, end)


def _is_same_event(ev_a: dict, identity_a: tuple, ev_b: dict, identity_b: tuple) -> bool:
    """Mesmo evento aparecendo nas duas listas.

    As agendas do casal são compartilhadas, então o evento de um também
    aparece na lista do outro. Comparar os dois não pode virar conflito.
    """
    if ev_a.get("id") and ev_a.get("id") == ev_b.get("id"):
        return True
    if ev_a.get("iCalUID") and ev_a.get("iCalUID") == ev_b.get("iCalUID"):
        return True
    return identity_a == identity_b


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
    reported_pairs = set()
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
        events_a = _timed_events(all_events[user_ids[0]], tz)
        events_b = _timed_events(all_events[user_ids[1]], tz)

        for ev_a, a_start, a_end in events_a:
            identity_a = _event_identity(ev_a, a_start, a_end)

            for ev_b, b_start, b_end in events_b:
                identity_b = _event_identity(ev_b, b_start, b_end)

                if _is_same_event(ev_a, identity_a, ev_b, identity_b):
                    continue

                if not (a_start < b_end and b_start < a_end):
                    continue

                # O mesmo par aparece espelhado nas duas listas; reporta uma vez.
                pair = frozenset({identity_a, identity_b})
                if pair in reported_pairs:
                    continue
                reported_pairs.add(pair)

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
            await check_new_events(app)
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
