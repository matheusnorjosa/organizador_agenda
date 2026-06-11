import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from src.agent import (
    check_reminders,
    cleanup_old_keys,
    notification_key,
    sent_notifications,
)


class TestCleanupOldKeys:
    def setup_method(self):
        sent_notifications.clear()

    def test_keeps_notification_key_from_today(self):
        key = notification_key("daily", "matheus", 7)
        sent_notifications.add(key)

        cleanup_old_keys()

        assert key in sent_notifications

    def test_removes_notification_key_from_previous_day(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        key = f"daily:matheus:{yesterday}:7"
        sent_notifications.add(key)

        cleanup_old_keys()

        assert key not in sent_notifications


class TestCheckReminders:
    def setup_method(self):
        sent_notifications.clear()

    def _make_app(self):
        app = MagicMock()
        app.bot = MagicMock()
        app.bot.send_message = AsyncMock()
        return app

    def _make_event(self, event_id: str, summary: str) -> dict:
        tz = ZoneInfo("America/Sao_Paulo")
        start = datetime.now(tz) + timedelta(hours=1)
        return {
            "id": event_id,
            "summary": summary,
            "start": {"dateTime": start.isoformat()},
        }

    def _patch_agent(self, get_events_mock, reminder_hours):
        return patch.multiple(
            "src.agent",
            REMINDER_HOURS=reminder_hours,
            load_users=MagicMock(return_value={"123": {"name": "matheus"}}),
            is_user_authenticated=MagicMock(return_value=True),
            is_user_silenced=MagicMock(return_value=False),
            get_events=get_events_mock,
        )

    def test_sends_day_events_once_across_loop_iterations(self):
        # Regressão: as chaves de deduplicação eram apagadas a cada ciclo
        # e os lembretes eram reenviados até a hora do evento.
        event = self._make_event("evt1", "Consulta")
        get_events_mock = MagicMock(return_value=[event])
        app = self._make_app()
        current_hour = datetime.now().hour

        async def run_two_cycles():
            cleanup_old_keys()
            await check_reminders(app)
            cleanup_old_keys()
            await check_reminders(app)

        with self._patch_agent(get_events_mock, [current_hour]):
            asyncio.run(run_two_cycles())

        assert app.bot.send_message.await_count == 1

    def test_sends_today_and_tomorrow_sections(self):
        today_event = self._make_event("evt1", "Consulta")
        tomorrow_event = self._make_event("evt2", "Reunião")

        def fake_get_events(user_id, days_ahead=1):
            if days_ahead == 1:
                return [today_event]
            return [today_event, tomorrow_event]

        app = self._make_app()
        current_hour = datetime.now().hour

        with self._patch_agent(MagicMock(side_effect=fake_get_events), [current_hour]):
            asyncio.run(check_reminders(app))

        assert app.bot.send_message.await_count == 2

    def test_does_not_send_outside_reminder_hours(self):
        event = self._make_event("evt1", "Consulta")
        get_events_mock = MagicMock(return_value=[event])
        app = self._make_app()
        other_hour = (datetime.now().hour + 2) % 24

        with self._patch_agent(get_events_mock, [other_hour]):
            asyncio.run(check_reminders(app))

        assert app.bot.send_message.await_count == 0
