import os
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKENS_DIR = os.path.join(os.path.dirname(__file__), "..", "tokens")
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
REDIRECT_URI = "http://localhost:1"


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


def is_user_authenticated(user_id: str) -> bool:
    token_path = get_token_path(user_id)
    return os.path.exists(token_path)


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


def format_event(event: dict) -> str:
    summary = event.get("summary", "Sem título")

    start = event["start"]
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        date_str = dt.strftime("%d/%m/%Y às %H:%M")
    else:
        date_str = start.get("date", "Data indefinida")

    return f"• {summary} — {date_str}"
