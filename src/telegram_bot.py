import json
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.calendar_api import (
    get_events,
    create_event,
    format_event,
    is_user_authenticated,
    generate_auth_url,
    complete_auth,
)

logger = logging.getLogger(__name__)

USERS_PATH = os.path.join(os.path.dirname(__file__), "..", "users.json")

WAITING_NAME = 0
WAITING_AUTH_URL = 1


def load_users() -> dict:
    if not os.path.exists(USERS_PATH):
        return {}
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(users: dict):
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def get_user_id(telegram_id: int) -> str | None:
    users = load_users()
    return users.get(str(telegram_id), {}).get("name")


def register_user(telegram_id: int, name: str):
    users = load_users()
    users[str(telegram_id)] = {"name": name}
    save_users(users)


async def check_user(update: Update) -> str | None:
    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)

    if not user_id:
        await update.message.reply_text(
            "Você ainda não está cadastrado. Use /auth para se registrar e conectar sua agenda."
        )
        return None

    if not is_user_authenticated(user_id):
        await update.message.reply_text(
            "Sua conta Google ainda não foi conectada. Use /auth para autenticar."
        )
        return None

    return user_id


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *Comandos disponíveis:*\n\n"
        "/auth — Cadastra e conecta sua conta Google\n"
        "/eventos — Lista os próximos eventos da agenda\n"
        "/criar <título> <dd/mm/aaaa> <hh:mm> — Cria um novo evento\n"
        "/ajuda — Mostra esta mensagem"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_auth_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)

    if user_id and is_user_authenticated(user_id):
        await update.message.reply_text("Sua conta Google já está conectada!")
        return ConversationHandler.END

    if user_id:
        return await send_auth_link(update, context, user_id)

    await update.message.reply_text(
        "Bem-vindo! Qual é o seu nome? (será usado para identificar sua agenda)"
    )
    return WAITING_NAME


async def cmd_auth_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().lower().replace(" ", "_")
    telegram_id = update.effective_user.id

    register_user(telegram_id, name)
    logger.info(f"Novo usuário registrado: {name} (Telegram ID: {telegram_id})")

    return await send_auth_link(update, context, name)


async def send_auth_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str):
    flow, auth_url = generate_auth_url()
    context.user_data["auth_flow"] = flow
    context.user_data["user_id"] = user_id

    await update.message.reply_text(
        f"Olá, *{user_id}*! 🔗 Clique no link abaixo para conectar sua conta Google:\n\n"
        f"{auth_url}\n\n"
        "Depois de autorizar, você será redirecionado para uma página que *não vai carregar*. "
        "Isso é normal! Copie a URL completa da barra de endereço e cole aqui.",
        parse_mode="Markdown",
    )

    return WAITING_AUTH_URL


async def cmd_auth_receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    redirect_url = update.message.text.strip()
    flow = context.user_data.get("auth_flow")
    user_id = context.user_data.get("user_id")

    if not flow or not user_id:
        await update.message.reply_text("Algo deu errado. Tente /auth novamente.")
        return ConversationHandler.END

    try:
        complete_auth(flow, redirect_url, user_id)
        await update.message.reply_text(
            f"✅ Conta Google conectada com sucesso, {user_id}! "
            "Agora você pode usar /eventos e /criar."
        )
    except Exception as e:
        logger.error(f"Erro na autenticação de {user_id}: {e}")
        await update.message.reply_text(
            "Erro ao processar a URL. Verifique se copiou a URL completa e tente /auth novamente."
        )

    return ConversationHandler.END


async def cmd_auth_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Autenticação cancelada.")
    return ConversationHandler.END


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

    auth_handler = ConversationHandler(
        entry_points=[CommandHandler("auth", cmd_auth_start)],
        states={
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_auth_receive_name),
            ],
            WAITING_AUTH_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_auth_receive_url),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cmd_auth_cancel)],
    )

    app.add_handler(auth_handler)
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("start", cmd_ajuda))
    app.add_handler(CommandHandler("eventos", cmd_eventos))
    app.add_handler(CommandHandler("criar", cmd_criar))

    return app
