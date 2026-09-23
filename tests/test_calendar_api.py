import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.calendar_api import (
    delete_event,
    parse_duration,
    resolve_guests,
    format_event,
    format_event_short,
    format_task,
    format_events_by_period,
    drop_finished_events,
    now_local,
    _calc_duration_str,
    _fetch_events_from_all_calendars,
    _get_period,
    _calendar_tag,
    set_calendar_hidden,
    update_event,
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

    def test_returns_days_and_hours_for_multi_day_event(self):
        # Antes saía "47h", que não se lê como quase dois dias.
        start = datetime(2026, 7, 31, 18, 0)
        end = datetime(2026, 8, 2, 17, 0)
        assert _calc_duration_str(start, end) == "1d23h"

    def test_returns_only_days_when_exact(self):
        start = datetime(2026, 7, 31, 18, 0)
        end = datetime(2026, 8, 2, 18, 0)
        assert _calc_duration_str(start, end) == "2d"


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


class TestAgendasOcultas:
    PRINCIPAL = "matheus@gmail.com"
    FERIADOS = "pt-br.brazilian#holiday@group.v.calendar.google.com"

    CALENDARS = [
        {"id": PRINCIPAL, "name": "Matheus", "access": "owner", "primary": True},
        {"id": FERIADOS, "name": "Feriados no Brasil", "access": "reader", "primary": False},
    ]
    EVENTS_BY_CALENDAR = {
        PRINCIPAL: [{"id": "dentista", "summary": "Dentista",
                     "start": {"dateTime": "2026-09-24T10:00:00-03:00"}}],
        FERIADOS: [{"id": "feriado", "summary": "Feriado",
                    "start": {"date": "2026-09-24"}}],
    }

    def _fetch_summaries(self, user_id: str, hidden_path: str) -> list[str]:
        def list_events(calendarId, **_kwargs):
            request = MagicMock()
            items = [dict(event) for event in self.EVENTS_BY_CALENDAR[calendarId]]
            request.execute.return_value = {"items": items}
            return request

        service = MagicMock()
        service.events.return_value.list.side_effect = list_events

        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path), \
             patch("src.calendar_api.get_calendar_service", return_value=service), \
             patch("src.calendar_api.list_all_calendars", return_value=self.CALENDARS):
            events = _fetch_events_from_all_calendars(
                user_id, "2026-09-24T00:00:00-03:00", "2026-09-24T23:59:59-03:00"
            )
        return sorted(event["summary"] for event in events)

    def test_sem_escolha_salva_mostra_todas_as_agendas(self, tmp_path):
        # Estado de quem nunca usou o /agendas, inclusive logo após o deploy.
        hidden_path = str(tmp_path / "estado" / "agendas_ocultas.json")
        assert self._fetch_summaries("matheus", hidden_path) == ["Dentista", "Feriado"]

    def test_evento_de_agenda_oculta_nao_aparece(self, tmp_path):
        hidden_path = str(tmp_path / "estado" / "agendas_ocultas.json")
        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path):
            set_calendar_hidden("matheus", self.FERIADOS, hidden=True)

        assert self._fetch_summaries("matheus", hidden_path) == ["Dentista"]

    def test_ocultar_vale_so_para_quem_ocultou(self, tmp_path):
        # As agendas são compartilhadas: a escolha de um não pode sumir com
        # os eventos do outro.
        hidden_path = str(tmp_path / "estado" / "agendas_ocultas.json")
        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path):
            set_calendar_hidden("matheus", self.FERIADOS, hidden=True)

        assert self._fetch_summaries("cecilia", hidden_path) == ["Dentista", "Feriado"]

    def test_mostrar_de_novo_traz_os_eventos_de_volta(self, tmp_path):
        hidden_path = str(tmp_path / "estado" / "agendas_ocultas.json")
        with patch("src.calendar_api.HIDDEN_CALENDARS_PATH", hidden_path):
            set_calendar_hidden("matheus", self.FERIADOS, hidden=True)
            set_calendar_hidden("matheus", self.FERIADOS, hidden=False)

        assert self._fetch_summaries("matheus", hidden_path) == ["Dentista", "Feriado"]

    def test_arquivo_ilegivel_nao_derruba_a_busca(self, tmp_path):
        # Lembretes e resumos dependem dessa busca; melhor mostrar agenda a
        # mais do que parar de avisar.
        hidden_file = tmp_path / "agendas_ocultas.json"
        hidden_file.write_text("{isso não é json", encoding="utf-8")

        assert self._fetch_summaries("matheus", str(hidden_file)) == ["Dentista", "Feriado"]


class TestUpdateEvent:
    FAMILIA = "familia@group.calendar.google.com"

    def _update(self, event: dict, updates: dict) -> dict:
        """Aplica a edição e devolve o corpo que seria enviado ao Google."""
        service = MagicMock()
        service.events.return_value.get.return_value.execute.return_value = event
        with patch("src.calendar_api.get_calendar_service", return_value=service):
            update_event("matheus", self.FAMILIA, "jantar", updates)

        get_kwargs = service.events.return_value.get.call_args.kwargs
        update_kwargs = service.events.return_value.update.call_args.kwargs
        assert get_kwargs["calendarId"] == update_kwargs["calendarId"] == self.FAMILIA
        self.send_updates = update_kwargs.get("sendUpdates")
        return update_kwargs["body"]

    # Regressão: agenda compartilhada pode devolver o horário em UTC. O jantar
    # de 09/10 às 22h de Fortaleza chega como 01h de 10/10, e a data ou o
    # horário antigo eram lidos nesse fuso.
    JANTAR_EM_UTC = {
        "summary": "Jantar",
        "start": {"dateTime": "2026-10-10T01:00:00Z"},
        "end": {"dateTime": "2026-10-10T02:30:00Z"},
    }

    def test_mudar_horario_mantem_a_data_local(self):
        body = self._update(dict(self.JANTAR_EM_UTC), {"time": "21:00"})

        assert body["start"] == {"dateTime": "2026-10-09T21:00:00", "timeZone": "America/Fortaleza"}
        assert body["end"] == {"dateTime": "2026-10-09T22:30:00", "timeZone": "America/Fortaleza"}

    def test_mudar_data_mantem_o_horario_local(self):
        body = self._update(dict(self.JANTAR_EM_UTC), {"date": "15/10/2026"})

        assert body["start"]["dateTime"] == "2026-10-15T22:00:00"
        assert body["end"]["dateTime"] == "2026-10-15T23:30:00"

    def test_mudar_data_de_evento_de_dia_inteiro_mantem_os_dias(self):
        # Regressão: evento de dia inteiro não tem "dateTime" e a edição quebrava.
        viagem = {
            "summary": "Viagem",
            "start": {"date": "2026-10-10"},
            "end": {"date": "2026-10-13"},
        }

        body = self._update(viagem, {"date": "20/10/2026"})

        assert body["start"] == {"date": "2026-10-20"}
        assert body["end"] == {"date": "2026-10-23"}

    def test_mudar_duracao_muda_so_o_fim_no_horario_local(self):
        body = self._update(dict(self.JANTAR_EM_UTC), {"duration": "1h"})

        assert body["start"] == self.JANTAR_EM_UTC["start"]
        assert body["end"] == {"dateTime": "2026-10-09T23:00:00", "timeZone": "America/Fortaleza"}

    def test_duracao_em_evento_de_dia_inteiro_e_recusada(self):
        viagem = {"summary": "Viagem", "start": {"date": "2026-10-10"}, "end": {"date": "2026-10-13"}}

        with pytest.raises(ValueError):
            self._update(viagem, {"duration": "2h"})

    def test_troca_local_e_apaga_descricao(self):
        jantar = {**self.JANTAR_EM_UTC, "description": "Levar sobremesa"}

        body = self._update(jantar, {"location": "Casa da vovó"})
        assert body["location"] == "Casa da vovó"

        body = self._update(jantar, {"description": ""})
        assert body["description"] == ""

    def test_convidar_nao_repete_quem_ja_esta_e_avisa_por_email(self):
        jantar = {**self.JANTAR_EM_UTC, "attendees": [{"email": "Mae@gmail.com"}]}

        body = self._update(jantar, {"add_attendees": ["mae@gmail.com", "joao@gmail.com"]})

        assert body["attendees"] == [{"email": "Mae@gmail.com"}, {"email": "joao@gmail.com"}]
        assert self.send_updates == "all"

    def test_mesmo_email_duas_vezes_entra_uma_vez_so(self):
        body = self._update(dict(self.JANTAR_EM_UTC), {"add_attendees": ["ana@x.com", "ANA@x.com"]})

        assert body["attendees"] == [{"email": "ana@x.com"}]

    def test_tirar_o_ultimo_convidado_tambem_avisa_por_email(self):
        # Sem o e-mail, quem saiu não fica sabendo.
        jantar = {**self.JANTAR_EM_UTC, "attendees": [{"email": "joao@gmail.com"}]}

        body = self._update(jantar, {"remove_attendees": ["JOAO@gmail.com"]})

        assert body["attendees"] == []
        assert self.send_updates == "all"

    def test_mudanca_em_evento_sem_convidados_nao_manda_email(self):
        self._update(dict(self.JANTAR_EM_UTC), {"title": "Jantar"})

        assert self.send_updates == "none"


class TestDeleteEvent:
    def _delete(self, event: dict) -> str:
        """Exclui e devolve para quem o Google mandaria e-mail."""
        service = MagicMock()
        service.events.return_value.get.return_value.execute.return_value = event
        with patch("src.calendar_api.get_calendar_service", return_value=service):
            delete_event("matheus", "familia@group.calendar.google.com", "jantar")
        return service.events.return_value.delete.call_args.kwargs["sendUpdates"]

    def test_quem_organiza_avisa_os_convidados_do_cancelamento(self):
        jantar = {"organizer": {"self": True}, "attendees": [{"email": "mae@gmail.com"}]}

        assert self._delete(jantar) == "all"

    def test_quem_foi_convidado_sai_sem_mandar_email(self):
        convite = {"organizer": {"email": "cecilia@gmail.com"}, "attendees": [{"email": "mae@gmail.com"}]}

        assert self._delete(convite) == "none"


class TestParseDuration:
    def test_entende_os_formatos_do_dia_a_dia(self):
        cases = {"1h": 60, "1h30": 90, "1h30min": 90, "90min": 90, "45": 45,
                 "2h 15min": 135, "1:30": 90, " 45 min ": 45}
        for text, minutes in cases.items():
            assert parse_duration(text) == timedelta(minutes=minutes), text

    def test_recusa_o_que_nao_e_duracao(self):
        for text in ["", "abc", "0", "0h", "uma hora", "-1h"]:
            with pytest.raises(ValueError):
                parse_duration(text)


class TestResolveGuests:
    CONTACTS = {"connections": [
        {"names": [{"displayName": "Mãe", "givenName": "Mãe"}],
         "emailAddresses": [{"value": "mae@gmail.com"}]},
        {"names": [{"displayName": "João Silva", "givenName": "João"}],
         "emailAddresses": [{"value": "joao@gmail.com"}]},
        {"names": [{"displayName": "João Pedro", "givenName": "João"}],
         "emailAddresses": [{"value": "jp@gmail.com"}]},
        {"names": [{"displayName": "Cecília Norjosa", "givenName": "Cecília"}],
         "emailAddresses": [{"value": "cecilia@gmail.com"}]},
        {"names": [{"displayName": "Sem E-mail"}]},
    ]}

    def _resolve(self, entries: list[str]) -> tuple[list[dict], list[str]]:
        people = MagicMock()
        people.people.return_value.connections.return_value.list.return_value.execute.return_value = self.CONTACTS
        with patch("src.calendar_api.get_people_service", return_value=people):
            return resolve_guests("matheus", entries)

    def test_troca_nome_por_email_sem_ligar_para_acento_nem_maiuscula(self):
        guests, problems = self._resolve(["mae", "CECILIA", "joão silva"])

        assert [guest["email"] for guest in guests] == ["mae@gmail.com", "cecilia@gmail.com", "joao@gmail.com"]
        assert problems == []

    def test_email_digitado_passa_direto(self):
        guests, problems = self._resolve(["ana@exemplo.com"])

        assert guests == [{"name": None, "email": "ana@exemplo.com"}]
        assert problems == []

    def test_nome_de_mais_de_um_contato_nao_vira_convite(self):
        # Convidar o João errado manda e-mail para outra pessoa.
        guests, problems = self._resolve(["joão"])

        assert guests == []
        assert "joao@gmail.com" in problems[0] and "jp@gmail.com" in problems[0]

    def test_nome_sem_contato_com_email_nao_vira_convite(self):
        guests, problems = self._resolve(["Ronaldo", "Sem E-mail"])

        assert guests == []
        assert len(problems) == 2


class TestEventosDeVariosDias:
    # Regressão: um evento de 31/07 18:00 a 02/08 17:00 era exibido como
    # "31/07/2026 18:00 às 17:00 (47h)" — parecia terminar antes de começar.

    CAPONGA = {
        "summary": "Caponga",
        "start": {"dateTime": "2026-07-31T18:00:00-03:00"},
        "end": {"dateTime": "2026-08-02T17:00:00-03:00"},
    }

    def test_format_event_mostra_a_data_do_fim(self):
        with patch.dict(os.environ, {"TIMEZONE": "America/Fortaleza"}):
            result = format_event(self.CAPONGA)
        assert "31/07/2026 18:00" in result
        assert "02/08/2026 17:00" in result
        assert "1d23h" in result

    def test_format_event_short_mostra_a_data_do_fim_sem_o_ano(self):
        with patch.dict(os.environ, {"TIMEZONE": "America/Fortaleza"}):
            result = format_event_short(self.CAPONGA)
        assert "18:00 às 02/08 17:00" in result

    def test_evento_do_mesmo_dia_nao_repete_a_data(self):
        event = {
            "summary": "Reunião",
            "start": {"dateTime": "2026-07-31T14:00:00-03:00"},
            "end": {"dateTime": "2026-07-31T15:00:00-03:00"},
        }
        with patch.dict(os.environ, {"TIMEZONE": "America/Fortaleza"}):
            result = format_event(event)
        assert "14:00 às 15:00" in result
        assert result.count("31/07") == 1


class TestDropFinishedEvents:
    def _event(self, event_id: str, end: str) -> dict:
        return {"id": event_id, "end": {"dateTime": end}}

    def test_remove_evento_ja_encerrado(self):
        referencia = datetime(2026, 7, 31, 20, 0, tzinfo=ZoneInfo("America/Fortaleza"))
        encerrado = self._event("passado", "2026-07-31T18:00:00-03:00")
        assert drop_finished_events([encerrado], referencia) == []

    def test_mantem_evento_em_andamento(self):
        referencia = datetime(2026, 7, 31, 20, 0, tzinfo=ZoneInfo("America/Fortaleza"))
        em_curso = self._event("agora", "2026-07-31T22:00:00-03:00")
        assert drop_finished_events([em_curso], referencia) == [em_curso]

    def test_mantem_evento_de_dia_todo_sem_hora_de_fim(self):
        referencia = datetime(2026, 7, 31, 20, 0, tzinfo=ZoneInfo("America/Fortaleza"))
        dia_todo = {"id": "feriado", "start": {"date": "2026-07-31"}}
        assert drop_finished_events([dia_todo], referencia) == [dia_todo]


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
