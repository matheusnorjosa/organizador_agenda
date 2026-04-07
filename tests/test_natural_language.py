import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

import pytest

from src.natural_language import _build_prompt, parse_event_from_text


class TestBuildPrompt:
    def test_includes_current_date(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_prompt("reunião amanhã", now)
        assert "10/04/2026" in prompt

    def test_includes_tomorrow_date(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_prompt("reunião amanhã", now)
        assert "11/04/2026" in prompt

    def test_includes_user_message(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_prompt("dentista sexta 10h", now)
        assert "dentista sexta 10h" in prompt


class TestParseEventFromText:
    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            result = await parse_event_from_text("reunião amanhã 14h")
            assert result is None

    @pytest.mark.asyncio
    async def test_parses_valid_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "title": "Reunião",
                        "date": "11/04/2026",
                        "time": "14:00",
                        "recurrence": None,
                    })
                }
            }]
        }

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "TIMEZONE": "America/Sao_Paulo"}):
            with patch("src.natural_language.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                    post=AsyncMock(return_value=mock_response)
                ))
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await parse_event_from_text("reunião amanhã 14h")

                assert result is not None
                assert result["title"] == "Reunião"
                assert result["date"] == "11/04/2026"
                assert result["time"] == "14:00"
