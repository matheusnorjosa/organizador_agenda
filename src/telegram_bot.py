import json
import logging
import os
from datetime import datetime, date, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.calendar_api import (
    get_events,
    get_events_for_date,
    create_event,
    delete_event,
    format_event,
    format_event_short,
    format_weekly_summary,
    format_daily_summary,
    get_free_slots,
    get_upcoming_birthdays,
    list_calendars,
    is_user_authenticated,
    generate_auth_url,
    complete_auth,
    wait_for_callback,
    check_scopes,
    get_timezone,
    get_tasks,
    create_task,
    complete_task,
    delete_task,
    format_task,
    DAYS_PT,
)

logger = logging.getLogger(__name__)

USERS_PATH = os.path.join(os.path.dirname(__file__), "..", "users.json")

WAITING_NAME = 0
WAITING_AUTH_URL = 1


# --- Gerenciamento de usuários ---

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


def is_user_silenced(telegram_id: int) -> bool:
    users = load_users()
    user_data = users.get(str(telegram_id), {})
    until = user_data.get("silenced_until")
    if not until:
        return False
    if datetime.fromisoformat(until) > datetime.now():
        return True
    # Expirou, limpa
    user_data.pop("silenced_until", None)
    save_users(users)
    return False


def set_silence(telegram_id: int, hours: int):
    users = load_users()
    user_data = users.get(str(telegram_id), {})
    user_data["silenced_until"] = (datetime.now() + timedelta(hours=hours)).isoformat()
    users[str(telegram_id)] = user_data
    save_users(users)


def remove_silence(telegram_id: int):
    users = load_users()
    user_data = users.get(str(telegram_id), {})
    user_data.pop("silenced_until", None)
    users[str(telegram_id)] = user_data
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

    missing = check_scopes(user_id)
    if missing:
        await update.message.reply_text(
            "⚠️ Novas permissões foram adicionadas ao bot. "
            "Use /auth novamente para atualizar o acesso à sua conta Google."
        )
        return None

    return user_id


# --- /ajuda ---

async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *Comandos disponíveis:*\n\n"
        "*Agenda:*\n"
        "/auth — Cadastra e conecta sua conta Google\n"
        "/eventos — Lista os próximos eventos\n"
        "/criar <título> <dd/mm/aaaa> <hh:mm> — Cria evento\n"
        "/excluir — Exclui um evento\n"
        "/livre — Horários vagos de hoje\n"
        "/semana — Programação da semana\n"
        "/semana\\_casal — Agenda do casal\n"
        "/aniversarios — Aniversários da semana\n\n"
        "*Tarefas:*\n"
        "/tarefas — Lista tarefas pendentes\n"
        "/nova\\_tarefa <título> — Cria tarefa\n"
        "/nova\\_tarefa <título> <dd/mm/aaaa> — Cria tarefa com prazo\n"
        "/concluir — Marca tarefa como concluída\n"
        "/excluir\\_tarefa — Remove uma tarefa\n\n"
        "*Outros:*\n"
        "/silencio <horas> — Pausa lembretes\n"
        "/ativar — Reativa lembretes\n"
        "/ajuda — Mostra esta mensagem"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# --- /auth ---

async def cmd_auth_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)

    needs_reauth = False
    if user_id and is_user_authenticated(user_id):
        missing = check_scopes(user_id)
        if not missing:
            await update.message.reply_text("Sua conta Google já está conectada!")
            return ConversationHandler.END
        needs_reauth = True

    if user_id:
        if needs_reauth:
            await update.message.reply_text(
                "⚠️ Novas permissões foram adicionadas. Vamos atualizar sua conexão."
            )
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
    # Tenta fluxo automático (servidor local captura o redirect)
    flow_local, auth_url_local = generate_auth_url(local=True)
    context.user_data["user_id"] = user_id

    await update.message.reply_text(
        f"Olá, {user_id}! 🔗 Clique no link abaixo para conectar sua conta Google:\n\n"
        f"{auth_url_local}\n\n"
        "Após autorizar, a página vai confirmar automaticamente. "
        "Aguardando autenticação..."
    )

    # Roda o servidor local em background para capturar o callback
    import asyncio
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, wait_for_callback, flow_local, user_id, 120)

    if success:
        await update.message.reply_text(
            f"✅ Conta Google conectada com sucesso, {user_id}! "
            "Agora você pode usar todos os comandos."
        )
        return ConversationHandler.END

    # Se o servidor local não captou (ex: usuário remoto), oferece fluxo manual
    flow_remote, auth_url_remote = generate_auth_url(local=False)
    context.user_data["auth_flow"] = flow_remote

    await update.message.reply_text(
        "⏱️ Não consegui capturar a autenticação automaticamente.\n\n"
        "Se você está em outro dispositivo, clique neste link:\n\n"
        f"{auth_url_remote}\n\n"
        "Depois de autorizar, copie a URL completa da barra de endereço e cole aqui."
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
            "Agora você pode usar todos os comandos."
        )
    except Exception as e:
        logger.error(f"Erro na autenticação de {user_id}: {e}")
        logger.error(f"URL recebida: {redirect_url}")
        await update.message.reply_text(
            f"Erro ao processar a URL: {e}\n\n"
            "Verifique se copiou a URL completa da barra de endereço e tente /auth novamente."
        )

    return ConversationHandler.END


async def cmd_auth_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Autenticação cancelada.")
    return ConversationHandler.END


# --- /eventos ---

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


# --- /criar ---

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
        calendars = list_calendars(user_id)
    except Exception as e:
        logger.error(f"Erro ao listar agendas de {user_id}: {e}")
        await update.message.reply_text("Erro ao acessar suas agendas. Tente novamente.")
        return

    context.user_data["pending_event"] = {
        "title": title,
        "date": date_str,
        "time": time_str,
    }

    if len(calendars) == 1:
        return await create_event_in_calendar(
            update, context, user_id, calendars[0]["id"], title, date_str, time_str
        )

    buttons = [
        [InlineKeyboardButton(cal["name"], callback_data=f"cal:{cal['id']}")]
        for cal in calendars
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        f"📅 Em qual agenda deseja criar *{title}*?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def callback_select_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user_id = get_user_id(telegram_id)
    if not user_id:
        await query.edit_message_text("Erro: usuário não encontrado.")
        return

    calendar_id = query.data.replace("cal:", "", 1)
    pending = context.user_data.get("pending_event")

    if not pending:
        await query.edit_message_text("Erro: nenhum evento pendente. Use /criar novamente.")
        return

    await create_event_in_calendar(
        update, context, user_id, calendar_id,
        pending["title"], pending["date"], pending["time"],
        edit_message=query,
    )


async def create_event_in_calendar(
    update, context, user_id, calendar_id, title, date_str, time_str, edit_message=None,
):
    try:
        created = create_event(user_id, title, date_str, time_str, calendar_id=calendar_id)
        summary = created.get("summary", title)
        text = f"✅ Evento criado: {summary} em {date_str} às {time_str}"
    except ValueError:
        text = "Formato inválido. Use: /criar <título> <dd/mm/aaaa> <hh:mm>"
    except Exception as e:
        logger.error(f"Erro ao criar evento para {user_id}: {e}")
        text = "Erro ao criar evento. Tente novamente."

    context.user_data.pop("pending_event", None)

    if edit_message:
        await edit_message.edit_message_text(text)
    else:
        await update.message.reply_text(text)


# --- /excluir ---

async def cmd_excluir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        events = get_events(user_id, days_ahead=30)
    except Exception as e:
        logger.error(f"Erro ao buscar eventos de {user_id}: {e}")
        await update.message.reply_text("Erro ao acessar a agenda. Tente novamente.")
        return

    if not events:
        await update.message.reply_text("Nenhum evento para excluir nos próximos 30 dias.")
        return

    buttons = []
    for ev in events[:15]:
        summary = ev.get("summary", "Sem título")
        start = ev["start"]
        if "dateTime" in start:
            dt = datetime.fromisoformat(start["dateTime"])
            label = f"{summary} — {dt.strftime('%d/%m %H:%M')}"
        else:
            label = f"{summary} — {start.get('date', '')}"

        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"del:{ev['id']}")]
        )

    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "🗑️ Qual evento deseja excluir?",
        reply_markup=keyboard,
    )


async def callback_delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user_id = get_user_id(telegram_id)
    if not user_id:
        await query.edit_message_text("Erro: usuário não encontrado.")
        return

    event_id = query.data.replace("del:", "", 1)

    try:
        delete_event(user_id, event_id)
        await query.edit_message_text("✅ Evento excluído com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao excluir evento para {user_id}: {e}")
        await query.edit_message_text("Erro ao excluir evento. Tente novamente.")


# --- /livre ---

async def cmd_livre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        today = date.today()
        free = get_free_slots(user_id, today)
    except Exception as e:
        logger.error(f"Erro ao buscar horários livres de {user_id}: {e}")
        await update.message.reply_text("Erro ao verificar horários. Tente novamente.")
        return

    if not free:
        await update.message.reply_text("Hoje não tem horário livre! 😅")
        return

    lines = ["🕐 *Horários livres hoje:*\n"]
    for slot in free:
        lines.append(f"• {slot}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# --- /semana ---

async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        text = format_weekly_summary(user_id)
    except Exception as e:
        logger.error(f"Erro ao gerar resumo semanal de {user_id}: {e}")
        await update.message.reply_text("Erro ao gerar resumo da semana. Tente novamente.")
        return

    await update.message.reply_text(text, parse_mode="Markdown")


# --- /semana_casal ---

async def cmd_semana_casal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    users = load_users()
    all_user_ids = [
        data["name"] for data in users.values()
        if data.get("name") and is_user_authenticated(data["name"])
    ]

    if len(all_user_ids) < 2:
        await update.message.reply_text("Só há um usuário autenticado. A agenda do casal precisa de dois!")
        return

    tz = get_timezone()
    today = datetime.now(tz).date()
    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    if monday == today:
        monday = today + timedelta(days=1)

    lines = ["👫 *Agenda do casal — próxima semana*\n"]

    for i in range(7):
        day = monday + timedelta(days=i)
        day_name = DAYS_PT[day.weekday()]
        date_str = day.strftime("%d/%m")

        lines.append(f"\n*{day_name} ({date_str}):*")

        for uid in all_user_ids:
            try:
                events = get_events_for_date(uid, day)
                lines.append(f"  __{uid}:__")
                if events:
                    for ev in events:
                        lines.append(f"  {format_event_short(ev).strip()}")
                else:
                    lines.append("    Sem eventos")
            except Exception:
                lines.append(f"  __{uid}:__ Erro ao acessar")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# --- /aniversarios ---

async def cmd_aniversarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        birthdays = get_upcoming_birthdays(user_id, days_ahead=7)
    except Exception as e:
        logger.error(f"Erro ao buscar aniversários de {user_id}: {e}")
        await update.message.reply_text("Erro ao buscar aniversários. Tente novamente.")
        return

    if not birthdays:
        await update.message.reply_text("Nenhum aniversário nos próximos 7 dias.")
        return

    lines = ["🎂 *Aniversários da semana:*\n"]
    for bday in birthdays:
        day_str = bday["date"].strftime("%d/%m")
        lines.append(f"• {bday['name']} — {day_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# --- /tarefas ---

async def cmd_tarefas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        tasks = get_tasks(user_id)
        pending = [t for t in tasks if t.get("status") != "completed"]
    except Exception as e:
        logger.error(f"Erro ao buscar tarefas de {user_id}: {e}")
        await update.message.reply_text("Erro ao acessar as tarefas. Tente novamente.")
        return

    if not pending:
        await update.message.reply_text("Nenhuma tarefa pendente!")
        return

    lines = ["📝 *Tarefas pendentes:*\n"]
    for t in pending:
        lines.append(f"  {format_task(t)}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# --- /nova_tarefa ---

async def cmd_nova_tarefa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    args = context.args

    if not args:
        await update.message.reply_text(
            "Uso: /nova_tarefa <título>\n"
            "Ou: /nova_tarefa <título> <dd/mm/aaaa>\n"
            "Exemplo: /nova_tarefa Comprar presente 15/04/2026"
        )
        return

    due_date = None
    try:
        datetime.strptime(args[-1], "%d/%m/%Y")
        due_date = args[-1]
        title = " ".join(args[:-1])
    except ValueError:
        title = " ".join(args)

    if not title:
        await update.message.reply_text("Informe o título da tarefa.")
        return

    try:
        created = create_task(user_id, title, due_date)
        text = f"✅ Tarefa criada: {created.get('title', title)}"
        if due_date:
            text += f" (prazo: {due_date})"
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Erro ao criar tarefa para {user_id}: {e}")
        await update.message.reply_text("Erro ao criar tarefa. Tente novamente.")


# --- /concluir ---

async def cmd_concluir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        tasks = get_tasks(user_id)
        pending = [t for t in tasks if t.get("status") != "completed"]
    except Exception as e:
        logger.error(f"Erro ao buscar tarefas de {user_id}: {e}")
        await update.message.reply_text("Erro ao acessar as tarefas. Tente novamente.")
        return

    if not pending:
        await update.message.reply_text("Nenhuma tarefa pendente para concluir!")
        return

    buttons = [
        [InlineKeyboardButton(t.get("title", "Sem título"), callback_data=f"done:{t['id']}")]
        for t in pending[:15]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "✅ Qual tarefa deseja concluir?",
        reply_markup=keyboard,
    )


async def callback_complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user_id = get_user_id(telegram_id)
    if not user_id:
        await query.edit_message_text("Erro: usuário não encontrado.")
        return

    task_id = query.data.replace("done:", "", 1)

    try:
        complete_task(user_id, task_id)
        await query.edit_message_text("✅ Tarefa concluída!")
    except Exception as e:
        logger.error(f"Erro ao concluir tarefa para {user_id}: {e}")
        await query.edit_message_text("Erro ao concluir tarefa. Tente novamente.")


# --- /excluir_tarefa ---

async def cmd_excluir_tarefa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await check_user(update)
    if not user_id:
        return

    try:
        tasks = get_tasks(user_id)
        pending = [t for t in tasks if t.get("status") != "completed"]
    except Exception as e:
        logger.error(f"Erro ao buscar tarefas de {user_id}: {e}")
        await update.message.reply_text("Erro ao acessar as tarefas. Tente novamente.")
        return

    if not pending:
        await update.message.reply_text("Nenhuma tarefa para excluir!")
        return

    buttons = [
        [InlineKeyboardButton(t.get("title", "Sem título"), callback_data=f"deltask:{t['id']}")]
        for t in pending[:15]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "🗑️ Qual tarefa deseja excluir?",
        reply_markup=keyboard,
    )


async def callback_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user_id = get_user_id(telegram_id)
    if not user_id:
        await query.edit_message_text("Erro: usuário não encontrado.")
        return

    task_id = query.data.replace("deltask:", "", 1)

    try:
        delete_task(user_id, task_id)
        await query.edit_message_text("✅ Tarefa excluída!")
    except Exception as e:
        logger.error(f"Erro ao excluir tarefa para {user_id}: {e}")
        await query.edit_message_text("Erro ao excluir tarefa. Tente novamente.")


# --- /silencio e /ativar ---

async def cmd_silencio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    telegram_id = update.effective_user.id

    if not args:
        await update.message.reply_text(
            "Uso: /silencio <horas>\n"
            "Exemplo: /silencio 24 (silencia por 24 horas)"
        )
        return

    try:
        hours = int(args[0])
    except ValueError:
        await update.message.reply_text("Informe um número válido de horas.")
        return

    set_silence(telegram_id, hours)
    await update.message.reply_text(
        f"🔇 Lembretes silenciados por {hours} horas. Use /ativar para reativar."
    )


async def cmd_ativar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    remove_silence(telegram_id)
    await update.message.reply_text("🔔 Lembretes reativados!")


# --- Bot setup ---

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
    app.add_handler(CommandHandler("excluir", cmd_excluir))
    app.add_handler(CommandHandler("livre", cmd_livre))
    app.add_handler(CommandHandler("semana", cmd_semana))
    app.add_handler(CommandHandler("semana_casal", cmd_semana_casal))
    app.add_handler(CommandHandler("aniversarios", cmd_aniversarios))
    app.add_handler(CommandHandler("tarefas", cmd_tarefas))
    app.add_handler(CommandHandler("nova_tarefa", cmd_nova_tarefa))
    app.add_handler(CommandHandler("concluir", cmd_concluir))
    app.add_handler(CommandHandler("excluir_tarefa", cmd_excluir_tarefa))
    app.add_handler(CommandHandler("silencio", cmd_silencio))
    app.add_handler(CommandHandler("ativar", cmd_ativar))
    app.add_handler(CallbackQueryHandler(callback_select_calendar, pattern=r"^cal:"))
    app.add_handler(CallbackQueryHandler(callback_delete_event, pattern=r"^del:"))
    app.add_handler(CallbackQueryHandler(callback_complete_task, pattern=r"^done:"))
    app.add_handler(CallbackQueryHandler(callback_delete_task, pattern=r"^deltask:"))

    return app
