import asyncio
import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from src.calendar_api import get_events, format_event, is_user_authenticated
from src.telegram_bot import create_bot

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60 * 60  # verifica a cada 1 hora
REMINDER_HOURS = [8, 20]  # horários em que os lembretes são enviados
USERS_PATH = os.path.join(os.path.dirname(__file__), "..", "users.json")


def load_users() -> dict:
    if not os.path.exists(USERS_PATH):
        return {}
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def send_reminder(bot, chat_id: str, events: list[dict], label: str):
    if not events:
        return

    lines = [format_event(ev) for ev in events]
    text = f"🔔 *{label}*\n\n" + "\n".join(lines)

    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    logger.info(f"Lembrete enviado para {chat_id}: {label} ({len(events)} eventos)")


async def check_and_notify(app):
    current_hour = datetime.now().hour

    if current_hour not in REMINDER_HOURS:
        return

    users = load_users()
    bot = app.bot

    for telegram_id, user_data in users.items():
        user_id = user_data.get("name")
        if not user_id or not is_user_authenticated(user_id):
            continue

        try:
            today_events = get_events(user_id, days_ahead=1)
            if today_events:
                await send_reminder(bot, telegram_id, today_events, "Eventos de hoje")

            tomorrow_events = get_events(user_id, days_ahead=2)
            tomorrow_only = [
                ev for ev in tomorrow_events if ev not in today_events
            ]
            if tomorrow_only:
                await send_reminder(bot, telegram_id, tomorrow_only, "Eventos de amanhã")

        except Exception as e:
            logger.error(f"Erro ao verificar eventos de {user_id}: {e}")


async def reminder_loop(app):
    logger.info("Loop de lembretes iniciado")
    while True:
        try:
            await check_and_notify(app)
        except Exception as e:
            logger.error(f"Erro no loop de lembretes: {e}")
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

        reminder_task = asyncio.create_task(reminder_loop(app))

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Encerrando...")
        finally:
            reminder_task.cancel()
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    loop.run_until_complete(run())


if __name__ == "__main__":
    main()
