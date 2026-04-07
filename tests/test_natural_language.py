import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

import pytest

from src.natural_language import (
    _build_intent_prompt,
    _build_event_prompt,
    parse_event_from_text,
    parse_intent,
    VALID_INTENTS,
)


class TestBuildIntentPrompt:
    def test_includes_current_date(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_intent_prompt("reunião amanhã", now)
        assert "10/04/2026" in prompt

    def test_includes_all_intents(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_intent_prompt("teste", now)
        for intent in VALID_INTENTS:
            assert intent in prompt

    def test_includes_user_message(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_intent_prompt("cancela o dentista", now)
        assert "cancela o dentista" in prompt


class TestBuildEventPrompt:
    def test_includes_current_date(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_event_prompt("reunião amanhã", now)
        assert "10/04/2026" in prompt

    def test_includes_tomorrow_date(self):
        now = datetime(2026, 4, 10, 14, 0)
        prompt = _build_event_prompt("reunião amanhã", now)
        assert "11/04/2026" in prompt


class TestParseIntent:
    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            result = await parse_intent("o que tenho hoje?")
            assert result is None

    @pytest.mark.asyncio
    async def test_parses_listar_intent(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "intent": "listar_eventos_hoje",
                        "title": None,
                        "date": None,
                        "time": None,
                        "recurrence": None,
                        "search_term": None,
                    })
                }
            }]
        }

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "TIMEZONE": "America/Sao_Paulo"}):
            with patch("src.natural_language.httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_instance.post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await parse_intent("o que tenho hoje?")
                assert result is not None
                assert result["intent"] == "listar_eventos_hoje"

    @pytest.mark.asyncio
    async def test_parses_criar_evento_intent(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "intent": "criar_evento",
                        "title": "Reunião",
                        "date": "11/04/2026",
                        "time": "14:00",
                        "recurrence": None,
                        "search_term": None,
                    })
                }
            }]
        }

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "TIMEZONE": "America/Sao_Paulo"}):
            with patch("src.natural_language.httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_instance.post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await parse_intent("marca reunião amanhã 14h")
                assert result is not None
                assert result["intent"] == "criar_evento"
                assert result["title"] == "Reunião"

    @pytest.mark.asyncio
    async def test_parses_excluir_intent_with_search_term(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "intent": "excluir_evento",
                        "title": None,
                        "date": None,
                        "time": None,
                        "recurrence": None,
                        "search_term": "dentista",
                    })
                }
            }]
        }

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "TIMEZONE": "America/Sao_Paulo"}):
            with patch("src.natural_language.httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_instance.post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await parse_intent("cancela o dentista")
                assert result is not None
                assert result["intent"] == "excluir_evento"
                assert result["search_term"] == "dentista"


class TestParseEventFromText:
    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            result = await parse_event_from_text("reunião amanhã 14h")
            assert result is None


class TestValidIntents:
    def test_has_all_expected_intents(self):
        assert "criar_evento" in VALID_INTENTS
        assert "editar_evento" in VALID_INTENTS
        assert "excluir_evento" in VALID_INTENTS
        assert "listar_eventos_hoje" in VALID_INTENTS
        assert "criar_tarefa" in VALID_INTENTS
        assert "desconhecido" in VALID_INTENTS
