import json
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from src.calendar_api import get_events, create_event, format_event, is_user_authenticated

logger = logging.getLogger(__name__)

USERS_PATH = os.path.join(os.path.dirname(__file__), "..", "users.json")


def load_users() -> dict:
    if not os.path.exists(USERS_PATH):
        return {}
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_user_id(telegram_id: int) -> str | None:
    users = load_users()
    return users.get(str(telegram_id), {}).get("name")


async def check_user(update: Update) -> str | None:
    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)

    if not user_id:
        await update.message.reply_text(
            "Você não está cadastrado. Peça ao administrador para te adicionar no users.json."
        )
        return None

    if not is_user_authenticated(user_id):
        await update.message.reply_text(
            "Sua conta Google ainda não foi autenticada. "
            "Peça ao administrador para rodar a autenticação."
        )
        return None

    return user_id


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *Comandos disponíveis:*\n\n"
        "/eventos — Lista os próximos eventos da agenda\n"
        "/criar <título> <dd/mm/aaaa> <hh:mm> — Cria um novo evento\n"
        "/ajuda — Mostra esta mensagem"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_eventos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        events = get_events(user_id, days_ahead=7)
    except Exception as e:
        logger.error(f"Erro ao buscar eventos de {user_id}: {e}")
        await update.message.reply_text("Erro ao acessar a agenda. Tente novamente.")
        return

    if not events:
        await update.message.reply_text("Nenhum evento nos próximos 7 dias.")
        return

    lines = [format_event(ev) for ev in events]
    text = "📅 *Próximos eventos:*\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_criar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    args = context.args

    if not args or len(args) < 3:
        await update.message.reply_text(
            "Uso: /criar <título> <dd/mm/aaaa> <hh:mm>\n"
            "Exemplo: /criar Reunião 10/04/2026 14:00"
        )
        return

    time_str = args[-1]
    date_str = args[-2]
    title = " ".join(args[:-2])

    try:
        created = create_event(user_id, title, date_str, time_str)
        summary = created.get("summary", title)
        await update.message.reply_text(f"✅ Evento criado: {summary} em {date_str} às {time_str}")
    except ValueError:
        await update.message.reply_text(
            "Formato inválido. Use: /criar <título> <dd/mm/aaaa> <hh:mm>"
        )
    except Exception as e:
        logger.error(f"Erro ao criar evento para {user_id}: {e}")
        await update.message.reply_text("Erro ao criar evento. Tente novamente.")


def create_bot(token: str) -> Application:
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("start", cmd_ajuda))
    app.add_handler(CommandHandler("eventos", cmd_eventos))
    app.add_handler(CommandHandler("criar", cmd_criar))

    return app
