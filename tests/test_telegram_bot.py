import asyncio
import json
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.calendar_api import get_hidden_calendars, set_calendar_hidden
from src.telegram_bot import (
    callback_cancel_calendar_removal,
    callback_confirm_calendar_removal,
    callback_toggle_calendar,
    callback_warn_calendar_removal,
    cmd_agendas,
    cmd_remover_agenda,
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


class TestComandoRemoverAgenda:
    MEU_EMAIL = "matheus@gmail.com"
    FAMILIA = "c_" + "9f" * 32 + "@group.calendar.google.com"
    FERIADOS = "pt-br.brazilian#holiday@group.v.calendar.google.com"
    TRABALHO_CECILIA = "c_" + "7a" * 32 + "@group.calendar.google.com"

    CALENDARS = [
        {"id": MEU_EMAIL, "name": "Matheus", "access": "owner", "primary": True},
        {"id": FAMILIA, "name": "Família", "access": "owner", "primary": False},
        {"id": FERIADOS, "name": "Feriados no Brasil", "access": "reader", "primary": False},
        # Compartilhada com "gerenciar compartilhamento": o Google dá permissão
        # de dono, mas a agenda é da Cecília.
        {"id": TRABALHO_CECILIA, "name": "Trabalho da Cecília", "access": "owner", "primary": False},
    ]

    def setup_method(self):
        self.data_owners = {self.FAMILIA: self.MEU_EMAIL, self.TRABALHO_CECILIA: "cecilia@gmail.com"}
        self.acl_error = False
        self.service = MagicMock()

        def request(body):
            fake = MagicMock()
            fake.execute.return_value = body
            return fake

        def get_calendar(calendarId):
            owner = self.data_owners.get(calendarId)
            return request({"id": calendarId, **({"dataOwner": owner} if owner else {})})

        def list_acl(calendarId):
            if self.acl_error:
                raise RuntimeError("403 Forbidden")
            return request({"items": [
                {"role": "owner", "scope": {"type": "user", "value": self.MEU_EMAIL}},
                {"role": "owner", "scope": {"type": "user", "value": calendarId}},
                {"role": "writer", "scope": {"type": "user", "value": "cecilia@gmail.com"}},
            ]})

        self.service.calendars.return_value.get.side_effect = get_calendar
        self.service.acl.return_value.list.side_effect = list_acl

    def _run(self, handler, update, hidden_path: str):
        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path), \
             patch("src.calendar_api.get_calendar_service", return_value=self.service), \
             patch("src.telegram_bot.list_all_calendars", return_value=self.CALENDARS), \
             patch("src.telegram_bot.get_user_id", return_value="matheus"), \
             patch("src.telegram_bot.check_user", AsyncMock(return_value="matheus")):
            asyncio.run(handler(update, MagicMock()))

    @staticmethod
    def _buttons_by_text(markup) -> dict:
        return {button.text: button for row in markup.inline_keyboard for button in row}

    def _open_menu(self, hidden_path: str) -> dict:
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        self._run(cmd_remover_agenda, update, hidden_path)
        return self._buttons_by_text(update.message.reply_text.call_args.kwargs["reply_markup"])

    def _tap(self, handler, callback_data: str, hidden_path: str) -> MagicMock:
        query = MagicMock()
        query.data = callback_data
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        self._run(handler, update, hidden_path)
        return query

    def _warn(self, name: str, hidden_path: str) -> tuple[str, dict]:
        """Escolhe a agenda no menu e devolve o aviso e os botões dele."""
        chosen = self._open_menu(hidden_path)[name]
        query = self._tap(callback_warn_calendar_removal, chosen.callback_data, hidden_path)
        buttons = self._buttons_by_text(query.edit_message_text.call_args.kwargs["reply_markup"])
        return query.edit_message_text.call_args.args[0], buttons

    def _confirm(self, name: str, hidden_path: str) -> MagicMock:
        _text, buttons = self._warn(name, hidden_path)
        confirm = next(button for text, button in buttons.items() if text != "Cancelar")
        return self._tap(callback_confirm_calendar_removal, confirm.callback_data, hidden_path)

    def _deleted(self) -> list[str]:
        calls = self.service.calendars.return_value.delete.call_args_list
        return [call.kwargs["calendarId"] for call in calls]

    def _unsubscribed(self) -> list[str]:
        calls = self.service.calendarList.return_value.delete.call_args_list
        return [call.kwargs["calendarId"] for call in calls]

    def test_menu_nao_oferece_a_agenda_principal(self, tmp_path):
        buttons = self._open_menu(str(tmp_path / "ocultas.json"))

        assert list(buttons) == ["Família", "Feriados no Brasil", "Trabalho da Cecília", "Cancelar"]

    def test_aviso_de_agenda_alheia_diz_que_os_eventos_continuam(self, tmp_path):
        text, buttons = self._warn("Feriados no Brasil", str(tmp_path / "ocultas.json"))

        assert "não são apagados" in text
        assert "Sim, remover da minha conta" in buttons
        assert self._deleted() == [] and self._unsubscribed() == []

    def test_aviso_de_agenda_propria_diz_quem_mais_perde_e_que_nao_tem_volta(self, tmp_path):
        text, buttons = self._warn("Família", str(tmp_path / "ocultas.json"))

        assert "para sempre" in text
        assert "Não dá para desfazer" in text
        assert "cecilia@gmail.com" in text
        assert self.MEU_EMAIL not in text and self.FAMILIA not in text
        assert "🗑️ Sim, excluir para todos" in buttons
        assert self._deleted() == [] and self._unsubscribed() == []

    def test_confirmar_agenda_alheia_so_tira_da_lista(self, tmp_path):
        query = self._confirm("Feriados no Brasil", str(tmp_path / "ocultas.json"))

        assert self._unsubscribed() == [self.FERIADOS]
        assert self._deleted() == []
        assert "removida da sua conta" in query.edit_message_text.call_args.args[0]

    def test_confirmar_agenda_propria_exclui(self, tmp_path):
        query = self._confirm("Família", str(tmp_path / "ocultas.json"))

        assert self._deleted() == [self.FAMILIA]
        assert self._unsubscribed() == []
        assert "foi excluída" in query.edit_message_text.call_args.args[0]

    def test_agenda_recebida_com_permissao_de_dono_nunca_e_excluida(self, tmp_path):
        # Decidir pela permissão apagaria a agenda da Cecília para todo mundo.
        hidden_path = str(tmp_path / "ocultas.json")
        text, _buttons = self._warn("Trabalho da Cecília", hidden_path)
        assert "não são apagados" in text

        self._confirm("Trabalho da Cecília", hidden_path)
        assert self._deleted() == []
        assert self._unsubscribed() == [self.TRABALHO_CECILIA]

    def test_reconhece_a_dona_mesmo_com_maiusculas_no_email(self, tmp_path):
        self.data_owners[self.FAMILIA] = "Matheus@Gmail.com"

        self._confirm("Família", str(tmp_path / "ocultas.json"))

        assert self._deleted() == [self.FAMILIA]

    def test_confirmacao_com_dado_malformado_responde_sem_remover(self, tmp_path):
        # Um cliente do Telegram pode mandar qualquer dado no toque; antes o
        # bot quebrava em silêncio e não respondia nada.
        query = self._tap(callback_confirm_calendar_removal, "rmagenda_ok:excluir", str(tmp_path / "o.json"))

        assert self._deleted() == [] and self._unsubscribed() == []
        assert query.edit_message_text.await_count == 1

    def test_agenda_sem_dono_informado_pelo_google_nao_e_excluida(self, tmp_path):
        del self.data_owners[self.FAMILIA]

        self._confirm("Família", str(tmp_path / "ocultas.json"))

        assert self._deleted() == []

    def test_confirmacao_de_aviso_desatualizado_nao_remove_nada(self, tmp_path):
        # O aviso dizia "só sai da lista". Se agora a ação seria excluir, a
        # pessoa não confirmou o que de fato aconteceria.
        hidden_path = str(tmp_path / "ocultas.json")
        self.data_owners[self.FAMILIA] = "cecilia@gmail.com"
        _text, buttons = self._warn("Família", hidden_path)
        self.data_owners[self.FAMILIA] = self.MEU_EMAIL

        query = self._tap(
            callback_confirm_calendar_removal,
            buttons["Sim, remover da minha conta"].callback_data,
            hidden_path,
        )

        assert self._deleted() == [] and self._unsubscribed() == []
        assert "Nada foi removido" in query.edit_message_text.call_args.args[0]

    def test_cancelar_nao_remove_nada(self, tmp_path):
        hidden_path = str(tmp_path / "ocultas.json")
        _text, buttons = self._warn("Família", hidden_path)

        query = self._tap(callback_cancel_calendar_removal, buttons["Cancelar"].callback_data, hidden_path)

        assert self._deleted() == [] and self._unsubscribed() == []
        assert "Nenhuma agenda foi removida" in query.edit_message_text.call_args.args[0]

    def test_aviso_sai_mesmo_sem_conseguir_ler_o_compartilhamento(self, tmp_path):
        self.acl_error = True

        text, _buttons = self._warn("Família", str(tmp_path / "ocultas.json"))

        assert "todo mundo que tem acesso" in text

    def test_remover_agenda_oculta_desfaz_a_escolha_do_agendas(self, tmp_path):
        # Se ela for adicionada de novo, não deve voltar escondida.
        hidden_path = str(tmp_path / "ocultas.json")
        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path):
            set_calendar_hidden("matheus", self.FERIADOS, hidden=True)

        self._confirm("Feriados no Brasil", hidden_path)

        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path):
            assert get_hidden_calendars("matheus") == set()
