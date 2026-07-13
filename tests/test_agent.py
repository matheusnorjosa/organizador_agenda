from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.agent import (
    check_daily_summary,
    notification_key,
    DAILY_SUMMARY_HOUR,
)

FORTALEZA = ZoneInfo("America/Fortaleza")


class TestNotificationKey:
    def test_uses_local_date_not_system_clock(self):
        # 22:00 em Fortaleza já é 01:00 UTC do dia seguinte. A chave deve
        # usar a data local (13), não a do relógio do sistema (14).
        local_now = datetime(2026, 7, 13, 22, 0, tzinfo=FORTALEZA)
        with patch("src.agent.now_local", return_value=local_now):
            key = notification_key("daily", "matheus", 7)
        assert "2026-07-13" in key


class TestCheckDailySummaryTiming:
    @pytest.mark.asyncio
    async def test_runs_at_local_summary_hour(self):
        local_now = datetime(2026, 7, 13, DAILY_SUMMARY_HOUR, 30, tzinfo=FORTALEZA)
        with patch("src.agent.now_local", return_value=local_now), \
                patch("src.agent.load_users", return_value={}) as mock_load:
            await check_daily_summary(MagicMock())
        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_run_when_utc_hour_matches_but_local_does_not(self):
        # No bug antigo o container rodava em UTC: às 7h UTC (4h em Fortaleza)
        # o resumo disparava cedo demais. Agora a decisão é pelo horário local.
        local_now = datetime(2026, 7, 13, 4, 0, tzinfo=FORTALEZA)
        with patch("src.agent.now_local", return_value=local_now), \
                patch("src.agent.load_users", return_value={}) as mock_load:
            await check_daily_summary(MagicMock())
        mock_load.assert_not_called()
