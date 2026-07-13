import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from src.calendar_api import (
    format_event,
    format_event_short,
    format_task,
    format_events_by_period,
    now_local,
    _calc_duration_str,
    _fetch_events_from_all_calendars,
    _get_period,
    _calendar_tag,
    RECURRENCE_MAP,
)


class TestCalcDurationStr:
    def test_returns_minutes_for_less_than_one_hour(self):
        start = datetime(2026, 4, 10, 14, 0)
        end = datetime(2026, 4, 10, 14, 30)
        assert _calc_duration_str(start, end) == "30min"

    def test_returns_hours_for_exact_hours(self):
        start = datetime(2026, 4, 10, 14, 0)
        end = datetime(2026, 4, 10, 16, 0)
        assert _calc_duration_str(start, end) == "2h"

    def test_returns_hours_and_minutes(self):
        start = datetime(2026, 4, 10, 14, 0)
        end = datetime(2026, 4, 10, 15, 30)
        assert _calc_duration_str(start, end) == "1h30min"


class TestGetPeriod:
    def test_morning(self):
        assert _get_period(8) == "manha"
        assert _get_period(11) == "manha"

    def test_afternoon(self):
        assert _get_period(12) == "tarde"
        assert _get_period(17) == "tarde"

    def test_evening(self):
        assert _get_period(18) == "noite"
        assert _get_period(23) == "noite"


class TestCalendarTag:
    def test_returns_empty_for_primary_calendar(self):
        event = {"summary": "Test"}
        assert _calendar_tag(event) == ""

    def test_returns_tag_for_other_calendar(self):
        event = {"summary": "Test", "_calendar_name": "Trabalho"}
        assert _calendar_tag(event) == " [Trabalho]"


class TestFormatEvent:
    def test_formats_timed_event(self):
        event = {
            "summary": "Reunião",
            "start": {"dateTime": "2026-04-10T14:00:00-03:00"},
            "end": {"dateTime": "2026-04-10T15:00:00-03:00"},
        }
        result = format_event(event)
        assert "Reunião" in result
        assert "14:00" in result
        assert "15:00" in result
        assert "1h" in result

    def test_formats_all_day_event(self):
        event = {
            "summary": "Feriado",
            "start": {"date": "2026-04-10"},
            "end": {"date": "2026-04-11"},
        }
        result = format_event(event)
        assert "Feriado" in result
        assert "dia todo" in result

    def test_shows_calendar_name_for_non_primary(self):
        event = {
            "summary": "Reunião",
            "_calendar_name": "Trabalho",
            "start": {"dateTime": "2026-04-10T14:00:00-03:00"},
            "end": {"dateTime": "2026-04-10T15:00:00-03:00"},
        }
        result = format_event(event)
        assert "[Trabalho]" in result

    def test_no_calendar_name_for_primary(self):
        event = {
            "summary": "Reunião",
            "start": {"dateTime": "2026-04-10T14:00:00-03:00"},
            "end": {"dateTime": "2026-04-10T15:00:00-03:00"},
        }
        result = format_event(event)
        assert "[" not in result


class TestFormatEventShort:
    def test_formats_timed_event(self):
        event = {
            "summary": "Dentista",
            "start": {"dateTime": "2026-04-10T10:00:00-03:00"},
            "end": {"dateTime": "2026-04-10T11:00:00-03:00"},
        }
        result = format_event_short(event)
        assert "10:00" in result
        assert "Dentista" in result

    def test_formats_all_day_event(self):
        event = {
            "summary": "Feriado",
            "start": {"date": "2026-04-10"},
        }
        result = format_event_short(event)
        assert "Dia todo" in result


class TestFormatTask:
    def test_pending_task_without_due(self):
        task = {"title": "Comprar leite", "status": "needsAction"}
        result = format_task(task)
        assert "⬜" in result
        assert "Comprar leite" in result

    def test_completed_task(self):
        task = {"title": "Comprar leite", "status": "completed"}
        result = format_task(task)
        assert "✅" in result

    def test_overdue_task(self):
        # Deriva a data de now_local() (fuso configurado), igual ao código,
        # para não depender do relógio do sistema onde o teste roda.
        yesterday = (now_local() - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z")
        task = {"title": "Tarefa atrasada", "status": "needsAction", "due": yesterday}
        result = format_task(task)
        assert "🔴" in result
        assert "ATRASADA" in result

    def test_due_today_task(self):
        today = now_local().strftime("%Y-%m-%dT00:00:00.000Z")
        task = {"title": "Tarefa hoje", "status": "needsAction", "due": today}
        result = format_task(task)
        assert "🟡" in result
        assert "HOJE" in result


class TestFormatEventsByPeriod:
    def test_separates_by_period(self):
        events = [
            {
                "summary": "Café",
                "start": {"dateTime": "2026-04-10T08:00:00-03:00"},
                "end": {"dateTime": "2026-04-10T09:00:00-03:00"},
            },
            {
                "summary": "Almoço",
                "start": {"dateTime": "2026-04-10T12:00:00-03:00"},
                "end": {"dateTime": "2026-04-10T13:00:00-03:00"},
            },
            {
                "summary": "Jantar",
                "start": {"dateTime": "2026-04-10T20:00:00-03:00"},
                "end": {"dateTime": "2026-04-10T21:00:00-03:00"},
            },
        ]
        result = format_events_by_period(events)
        assert "Manhã" in result
        assert "Tarde" in result
        assert "Noite" in result
        assert "Café" in result
        assert "Almoço" in result
        assert "Jantar" in result

    def test_includes_all_day_events(self):
        events = [
            {
                "summary": "Feriado",
                "start": {"date": "2026-04-10"},
                "end": {"date": "2026-04-11"},
            },
        ]
        result = format_events_by_period(events)
        assert "Dia todo" in result
        assert "Feriado" in result


class TestTimezoneConversion:
    # Regressão: eventos de agendas compartilhadas chegavam em UTC e o
    # horário era exibido sem conversão (17:00 em vez de 14:00).

    def test_format_event_converts_utc_to_configured_timezone(self):
        event = {
            "summary": "US abdominal",
            "start": {"dateTime": "2026-06-12T17:00:00Z"},
            "end": {"dateTime": "2026-06-12T18:00:00Z"},
        }
        with patch.dict(os.environ, {"TIMEZONE": "America/Sao_Paulo"}):
            result = format_event(event)
        assert "14:00" in result
        assert "15:00" in result
        assert "12/06/2026" in result

    def test_format_event_short_converts_utc_to_configured_timezone(self):
        event = {
            "summary": "US abdominal",
            "start": {"dateTime": "2026-06-12T17:00:00Z"},
            "end": {"dateTime": "2026-06-12T18:00:00Z"},
        }
        with patch.dict(os.environ, {"TIMEZONE": "America/Sao_Paulo"}):
            result = format_event_short(event)
        assert "14:00" in result
        assert "15:00" in result

    def test_format_events_by_period_classifies_by_local_hour(self):
        event = {
            "summary": "Consulta",
            "start": {"dateTime": "2026-06-12T14:00:00Z"},
            "end": {"dateTime": "2026-06-12T15:00:00Z"},
        }
        with patch.dict(os.environ, {"TIMEZONE": "America/Sao_Paulo"}):
            result = format_events_by_period([event])
        assert "Manhã" in result
        assert "Tarde" not in result

    def test_format_event_keeps_time_already_in_configured_timezone(self):
        event = {
            "summary": "Reunião",
            "start": {"dateTime": "2026-06-12T14:00:00-03:00"},
            "end": {"dateTime": "2026-06-12T15:00:00-03:00"},
        }
        with patch.dict(os.environ, {"TIMEZONE": "America/Sao_Paulo"}):
            result = format_event(event)
        assert "14:00" in result
        assert "15:00" in result


class TestFetchEventsTimezone:
    def test_requests_events_in_configured_timezone(self):
        calendars = [{"id": "primary", "name": "Pessoal", "access": "owner", "primary": True}]
        mock_service = MagicMock()
        mock_service.events.return_value.list.return_value.execute.return_value = {"items": []}

        with patch.dict(os.environ, {"TIMEZONE": "America/Sao_Paulo"}), \
             patch("src.calendar_api.get_calendar_service", return_value=mock_service), \
             patch("src.calendar_api.list_all_calendars", return_value=calendars):
            _fetch_events_from_all_calendars(
                "matheus", "2026-06-12T00:00:00Z", "2026-06-13T00:00:00Z"
            )

        _, kwargs = mock_service.events.return_value.list.call_args
        assert kwargs["timeZone"] == "America/Sao_Paulo"


class TestRecurrenceMap:
    def test_has_expected_keys(self):
        assert "diario" in RECURRENCE_MAP
        assert "semanal" in RECURRENCE_MAP
        assert "quinzenal" in RECURRENCE_MAP
        assert "mensal" in RECURRENCE_MAP

    def test_values_are_rrule_format(self):
        for value in RECURRENCE_MAP.values():
            assert value.startswith("RRULE:")


class TestNowLocal:
    def test_returns_timezone_aware_datetime(self):
        with patch.dict(os.environ, {"TIMEZONE": "America/Fortaleza"}):
            assert now_local().tzinfo is not None

    def test_uses_configured_timezone_offset(self):
        # Fortaleza é UTC-3 o ano todo (Brasil não tem mais horário de verão)
        with patch.dict(os.environ, {"TIMEZONE": "America/Fortaleza"}):
            assert now_local().utcoffset() == timedelta(hours=-3)


class TestFormatTaskTimezone:
    def test_due_today_not_marked_overdue_near_midnight(self):
        # 22:00 em Fortaleza já é 01:00 UTC do dia seguinte. Uma tarefa que
        # vence hoje (13) não pode virar ATRASADA só porque o relógio do
        # servidor (UTC) já passou para o dia 14.
        local_now = datetime(2026, 7, 13, 22, 0, tzinfo=ZoneInfo("America/Fortaleza"))
        task = {
            "title": "Pagar conta",
            "status": "needsAction",
            "due": "2026-07-13T00:00:00.000Z",
        }
        with patch("src.calendar_api.now_local", return_value=local_now):
            result = format_task(task)
        assert "HOJE" in result
        assert "ATRASADA" not in result
