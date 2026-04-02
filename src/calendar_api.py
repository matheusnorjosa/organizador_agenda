import os
from datetime import datetime, timedelta, date, time as dt_time
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/tasks",
]
TOKENS_DIR = os.path.join(os.path.dirname(__file__), "..", "tokens")
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
REDIRECT_URI = "http://localhost:1"

DAYS_PT = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}


def get_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))


def get_token_path(user_id: str) -> str:
    os.makedirs(TOKENS_DIR, exist_ok=True)
    return os.path.join(TOKENS_DIR, f"{user_id}.json")


def generate_auth_url() -> tuple[Flow, str]:
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_PATH,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return flow, auth_url


def complete_auth(flow: Flow, redirect_url: str, user_id: str):
    parsed = urlparse(redirect_url)
    code = parse_qs(parsed.query).get("code", [None])[0]

    if not code:
        raise ValueError("Código de autorização não encontrado na URL.")

    flow.fetch_token(code=code)
    creds = flow.credentials

    token_path = get_token_path(user_id)
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())

    return creds


def get_calendar_service(user_id: str):
    token_path = get_token_path(user_id)
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())
        else:
            raise RuntimeError(
                f"Usuário '{user_id}' não autenticado. Use /auth no Telegram."
            )

    return build("calendar", "v3", credentials=creds)


def get_people_service(user_id: str):
    token_path = get_token_path(user_id)
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

    return build("people", "v1", credentials=creds)


def is_user_authenticated(user_id: str) -> bool:
    token_path = get_token_path(user_id)
    return os.path.exists(token_path)


# --- Buscar eventos ---

def get_events(user_id: str, days_ahead: int = 1) -> list[dict]:
    service = get_calendar_service(user_id)

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return result.get("items", [])


def get_events_for_date(user_id: str, target_date: date) -> list[dict]:
    tz = get_timezone()
    start = datetime.combine(target_date, dt_time.min, tzinfo=tz)
    end = datetime.combine(target_date, dt_time.max, tzinfo=tz)

    service = get_calendar_service(user_id)
    result = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return result.get("items", [])


def get_events_between(user_id: str, start_date: date, end_date: date) -> list[dict]:
    tz = get_timezone()
    start = datetime.combine(start_date, dt_time.min, tzinfo=tz)
    end = datetime.combine(end_date, dt_time.max, tzinfo=tz)

    service = get_calendar_service(user_id)
    result = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return result.get("items", [])


# --- Criar e excluir eventos ---

def list_calendars(user_id: str) -> list[dict]:
    service = get_calendar_service(user_id)
    result = service.calendarList().list().execute()
    calendars = result.get("items", [])
    return [
        {"id": cal["id"], "name": cal.get("summary", "Sem nome")}
        for cal in calendars
        if cal.get("accessRole") in ("owner", "writer")
    ]


def create_event(
    user_id: str, title: str, date: str, time: str,
    calendar_id: str = "primary", duration_minutes: int = 60,
) -> dict:
    service = get_calendar_service(user_id)

    start_dt = datetime.strptime(f"{date} {time}", "%d/%m/%Y %H:%M")
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    timezone = os.getenv("TIMEZONE", "America/Sao_Paulo")

    event = {
        "summary": title,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": timezone,
        },
    }

    created = service.events().insert(calendarId=calendar_id, body=event).execute()
    return created


def delete_event(user_id: str, event_id: str):
    service = get_calendar_service(user_id)
    service.events().delete(calendarId="primary", eventId=event_id).execute()


# --- Horários livres ---

def get_free_slots(user_id: str, target_date: date, work_start: int = 8, work_end: int = 22) -> list[str]:
    events = get_events_for_date(user_id, target_date)
    tz = get_timezone()

    busy = []
    for ev in events:
        start = ev["start"]
        end = ev["end"]
        if "dateTime" in start:
            s = datetime.fromisoformat(start["dateTime"]).astimezone(tz)
            e = datetime.fromisoformat(end["dateTime"]).astimezone(tz)
            busy.append((s.hour * 60 + s.minute, e.hour * 60 + e.minute))

    busy.sort()

    free = []
    cursor = work_start * 60

    for start_min, end_min in busy:
        if start_min > cursor:
            free.append(f"{cursor // 60:02d}:{cursor % 60:02d} — {start_min // 60:02d}:{start_min % 60:02d}")
        cursor = max(cursor, end_min)

    if cursor < work_end * 60:
        free.append(f"{cursor // 60:02d}:{cursor % 60:02d} — {work_end:02d}:00")

    return free


# --- Aniversários ---

def get_birthdays(user_id: str) -> list[dict]:
    try:
        service = get_people_service(user_id)
        results = service.people().connections().list(
            resourceName="people/me",
            pageSize=1000,
            personFields="names,birthdays",
        ).execute()

        contacts = results.get("connections", [])
        birthdays = []

        for person in contacts:
            names = person.get("names", [])
            bdays = person.get("birthdays", [])
            if not names or not bdays:
                continue

            name = names[0].get("displayName", "Sem nome")
            for bday in bdays:
                bdate = bday.get("date", {})
                month = bdate.get("month")
                day = bdate.get("day")
                if month and day:
                    birthdays.append({"name": name, "month": month, "day": day})
                    break

        return birthdays
    except Exception:
        return []


def get_upcoming_birthdays(user_id: str, days_ahead: int = 7) -> list[dict]:
    all_birthdays = get_birthdays(user_id)
    today = date.today()
    upcoming = []

    for bday in all_birthdays:
        for offset in range(days_ahead):
            check_date = today + timedelta(days=offset)
            if bday["month"] == check_date.month and bday["day"] == check_date.day:
                upcoming.append({
                    "name": bday["name"],
                    "date": check_date,
                })
                break

    upcoming.sort(key=lambda x: x["date"])
    return upcoming


# --- Formatação ---

def format_event(event: dict) -> str:
    summary = event.get("summary", "Sem título")

    start = event["start"]
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        date_str = dt.strftime("%d/%m/%Y às %H:%M")
    else:
        date_str = start.get("date", "Data indefinida")

    return f"• {summary} — {date_str}"


def format_event_short(event: dict) -> str:
    summary = event.get("summary", "Sem título")

    start = event["start"]
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        return f"  {dt.strftime('%H:%M')} — {summary}"
    return f"  Dia todo — {summary}"


def format_weekly_summary(user_id: str) -> str:
    tz = get_timezone()
    today = datetime.now(tz).date()

    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    if monday == today:
        monday = today + timedelta(days=1)

    lines = ["📋 *Programação da semana*\n"]

    has_events = False
    for i in range(7):
        day = monday + timedelta(days=i)
        day_name = DAYS_PT[day.weekday()]
        date_str = day.strftime("%d/%m")

        events = get_events_for_date(user_id, day)
        lines.append(f"\n*{day_name} ({date_str}):*")

        if events:
            has_events = True
            for ev in events:
                lines.append(format_event_short(ev))
        else:
            lines.append("  Sem eventos")

    if not has_events:
        return "📋 *Programação da semana*\n\nSemana livre! Nenhum evento agendado."

    return "\n".join(lines)


def get_tasks_service(user_id: str):
    token_path = get_token_path(user_id)
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

    return build("tasks", "v1", credentials=creds)


# --- Tarefas (Google Tasks) ---

def list_task_lists(user_id: str) -> list[dict]:
    service = get_tasks_service(user_id)
    result = service.tasklists().list().execute()
    return [
        {"id": tl["id"], "name": tl.get("title", "Sem nome")}
        for tl in result.get("items", [])
    ]


def get_tasks(user_id: str, task_list_id: str = "@default", show_completed: bool = False) -> list[dict]:
    service = get_tasks_service(user_id)
    result = service.tasks().list(
        tasklist=task_list_id,
        showCompleted=show_completed,
        showHidden=False,
    ).execute()
    return result.get("items", [])


def create_task(user_id: str, title: str, due_date: str = None, task_list_id: str = "@default") -> dict:
    service = get_tasks_service(user_id)

    task = {"title": title}

    if due_date:
        dt = datetime.strptime(due_date, "%d/%m/%Y")
        task["due"] = dt.strftime("%Y-%m-%dT00:00:00.000Z")

    created = service.tasks().insert(tasklist=task_list_id, body=task).execute()
    return created


def complete_task(user_id: str, task_id: str, task_list_id: str = "@default"):
    service = get_tasks_service(user_id)
    task = service.tasks().get(tasklist=task_list_id, task=task_id).execute()
    task["status"] = "completed"
    service.tasks().update(tasklist=task_list_id, task=task_id, body=task).execute()


def delete_task(user_id: str, task_id: str, task_list_id: str = "@default"):
    service = get_tasks_service(user_id)
    service.tasks().delete(tasklist=task_list_id, task=task_id).execute()


def format_task(task: dict) -> str:
    title = task.get("title", "Sem título")
    status = "✅" if task.get("status") == "completed" else "⬜"
    due = task.get("due")
    if due:
        dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
        return f"{status} {title} — até {dt.strftime('%d/%m/%Y')}"
    return f"{status} {title}"


def format_daily_summary(user_id: str) -> str:
    tz = get_timezone()
    today = datetime.now(tz).date()
    day_name = DAYS_PT[today.weekday()]
    date_str = today.strftime("%d/%m/%Y")

    events = get_events_for_date(user_id, today)

    lines = [f"☀️ *Bom dia! {day_name}, {date_str}*\n"]

    if events:
        lines.append("📅 *Eventos:*")
        for ev in events:
            lines.append(format_event_short(ev))
    else:
        lines.append("📅 Nenhum evento hoje.")

    try:
        tasks = get_tasks(user_id)
        pending = [t for t in tasks if t.get("status") != "completed"]
        if pending:
            lines.append("\n📝 *Tarefas pendentes:*")
            for t in pending:
                lines.append(f"  {format_task(t)}")
    except Exception:
        pass

    return "\n".join(lines)
