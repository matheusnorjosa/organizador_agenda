import asyncio
import json
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.calendar_api import get_hidden_calendars
from src.telegram_bot import (
    callback_toggle_calendar,
    cmd_agendas,
    load_users,
    get_user_id,
    is_user_silenced,
)


class TestLoadUsers:
    def test_returns_empty_dict_when_no_file(self, tmp_path):
        fake_path = str(tmp_path / "nonexistent.json")
        with patch("src.telegram_bot.USERS_PATH", fake_path):
            result = load_users()
            assert result == {}

    def test_loads_users_from_file(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({
            "123": {"name": "matheus"},
            "456": {"name": "cecilia"},
        }))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            result = load_users()
            assert result["123"]["name"] == "matheus"
            assert result["456"]["name"] == "cecilia"


class TestGetUserId:
    def test_returns_name_for_existing_user(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({"123": {"name": "matheus"}}))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert get_user_id(123) == "matheus"

    def test_returns_none_for_unknown_user(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({"123": {"name": "matheus"}}))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert get_user_id(999) is None


class TestIsUserSilenced:
    def test_returns_false_when_not_silenced(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({"123": {"name": "matheus"}}))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert is_user_silenced(123) is False

    def test_returns_true_when_silenced(self, tmp_path):
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({
            "123": {"name": "matheus", "silenced_until": future}
        }))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert is_user_silenced(123) is True

    def test_returns_false_when_silence_expired(self, tmp_path):
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({
            "123": {"name": "matheus", "silenced_until": past}
        }))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert is_user_silenced(123) is False


class TestComandoAgendas:
    PRINCIPAL = "matheus@gmail.com"
    # Formato das agendas criadas hoje no Google: passa dos 64 bytes que o
    # Telegram aceita como dado de um botão.
    FAMILIA = "c_" + "9f" * 32 + "@group.calendar.google.com"
    FERIADOS = "pt-br.brazilian#holiday@group.v.calendar.google.com"

    CALENDARS = [
        {"id": PRINCIPAL, "name": "Matheus", "access": "owner", "primary": True},
        {"id": FAMILIA, "name": "Família", "access": "writer", "primary": False},
        {"id": FERIADOS, "name": "Feriados no Brasil", "access": "reader", "primary": False},
    ]

    @staticmethod
    def _buttons(markup) -> list:
        return [row[0] for row in markup.inline_keyboard]

    def _open_menu(self, hidden_path: str) -> list:
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path), \
             patch("src.telegram_bot.check_user", AsyncMock(return_value="matheus")), \
             patch("src.telegram_bot.list_all_calendars", return_value=self.CALENDARS):
            asyncio.run(cmd_agendas(update, MagicMock()))

        return self._buttons(update.message.reply_text.call_args.kwargs["reply_markup"])

    def _tap(self, button, hidden_path: str, calendars: list[dict]) -> MagicMock:
        query = MagicMock()
        query.data = button.callback_data
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.edit_message_reply_markup = AsyncMock()
        update = MagicMock()
        update.callback_query = query

        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path), \
             patch("src.telegram_bot.get_user_id", return_value="matheus"), \
             patch("src.telegram_bot.list_all_calendars", return_value=calendars):
            asyncio.run(callback_toggle_calendar(update, MagicMock()))

        return query

    def _hidden(self, hidden_path: str) -> set[str]:
        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path):
            return get_hidden_calendars("matheus")

    def test_menu_nao_oferece_ocultar_a_agenda_principal(self, tmp_path):
        buttons = self._open_menu(str(tmp_path / "agendas_ocultas.json"))

        assert [button.text for button in buttons] == ["✅ Família", "✅ Feriados no Brasil"]

    def test_botao_cabe_no_limite_do_telegram_mesmo_com_id_longo(self, tmp_path):
        buttons = self._open_menu(str(tmp_path / "agendas_ocultas.json"))

        assert all(len(button.callback_data.encode("utf-8")) <= 64 for button in buttons)

    def test_tocar_oculta_a_agenda_e_tocar_de_novo_mostra(self, tmp_path):
        hidden_path = str(tmp_path / "agendas_ocultas.json")
        feriados = self._open_menu(hidden_path)[1]

        query = self._tap(feriados, hidden_path, self.CALENDARS)
        assert self._hidden(hidden_path) == {self.FERIADOS}
        markup = query.edit_message_reply_markup.call_args.kwargs["reply_markup"]
        assert [button.text for button in self._buttons(markup)] == [
            "✅ Família", "🚫 Feriados no Brasil (oculta)",
        ]

        query = self._tap(feriados, hidden_path, self.CALENDARS)
        assert self._hidden(hidden_path) == set()
        markup = query.edit_message_reply_markup.call_args.kwargs["reply_markup"]
        assert [button.text for button in self._buttons(markup)] == [
            "✅ Família", "✅ Feriados no Brasil",
        ]

    def test_menu_antigo_de_agenda_que_saiu_da_conta_avisa_o_usuario(self, tmp_path):
        hidden_path = str(tmp_path / "agendas_ocultas.json")
        feriados = self._open_menu(hidden_path)[1]
        without_feriados = [cal for cal in self.CALENDARS if cal["id"] != self.FERIADOS]

        query = self._tap(feriados, hidden_path, without_feriados)

        assert self._hidden(hidden_path) == set()
        assert "não está mais" in query.edit_message_text.call_args.args[0]
