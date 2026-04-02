import os
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKENS_DIR = os.path.join(os.path.dirname(__file__), "..", "tokens")
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "..", "credentials.json")


def get_token_path(user_id: str) -> str:
    os.makedirs(TOKENS_DIR, exist_ok=True)
    return os.path.join(TOKENS_DIR, f"{user_id}.json")


def get_calendar_service(user_id: str):
    token_path = get_token_path(user_id)
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

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


def create_event(user_id: str, title: str, date: str, time: str, duration_minutes: int = 60) -> dict:
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

    created = service.events().insert(calendarId="primary", body=event).execute()
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
