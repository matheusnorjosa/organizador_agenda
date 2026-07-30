import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from src.agent import (
    announced_new_events,
    check_couple_conflicts,
    check_daily_summary,
    check_new_events,
    check_reminders,
    cleanup_old_keys,
    notification_key,
    sent_notifications,
    DAILY_SUMMARY_HOUR,
)
from src.calendar_api import now_local


class TestCleanupOldKeys:
    def setup_method(self):
        sent_notifications.clear()

    def test_keeps_notification_key_from_today(self):
        key = notification_key("daily", "matheus", 7)
        sent_notifications.add(key)

        cleanup_old_keys()

        assert key in sent_notifications

    def test_removes_notification_key_from_previous_day(self):
        # Deriva do fuso local, igual ao cleanup_old_keys: com o relógio do
        # sistema em UTC a data vira 3h antes e o teste ficaria instável.
        yesterday = (now_local().date() - timedelta(days=1)).isoformat()
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

    def _make_event(self, event_id: str, summary: str, start: datetime | None = None) -> dict:
        start = start or now_local() + timedelta(hours=1)
        return {
            "id": event_id,
            "summary": summary,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        }

    def _patch_agent(self, events_for_date_mock, reminder_hours):
        return patch.multiple(
            "src.agent",
            REMINDER_HOURS=reminder_hours,
            load_users=MagicMock(return_value={"123": {"name": "matheus"}}),
            is_user_authenticated=MagicMock(return_value=True),
            is_user_silenced=MagicMock(return_value=False),
            get_events_for_date=events_for_date_mock,
        )

    def _only_on(self, day, events: list[dict]):
        """Mock de agenda: os eventos existem apenas no dia informado."""
        return MagicMock(
            side_effect=lambda user_id, check_date: events if check_date == day else []
        )

    def test_sends_day_events_once_across_loop_iterations(self):
        # Regressão: as chaves de deduplicação eram apagadas a cada ciclo
        # e os lembretes eram reenviados até a hora do evento.
        today = now_local().date()
        event = self._make_event("evt1", "Consulta")
        app = self._make_app()
        current_hour = now_local().hour

        async def run_two_cycles():
            cleanup_old_keys()
            await check_reminders(app)
            cleanup_old_keys()
            await check_reminders(app)

        with self._patch_agent(self._only_on(today, [event]), [current_hour]):
            asyncio.run(run_two_cycles())

        assert app.bot.send_message.await_count == 1

    def test_sends_today_and_tomorrow_sections(self):
        today = now_local().date()
        today_event = self._make_event("evt1", "Consulta")
        tomorrow_event = self._make_event(
            "evt2", "Reunião", start=now_local() + timedelta(days=1)
        )

        def fake_events(user_id, check_date):
            if check_date == today:
                return [today_event]
            return [tomorrow_event]

        app = self._make_app()
        current_hour = now_local().hour

        with self._patch_agent(MagicMock(side_effect=fake_events), [current_hour]):
            asyncio.run(check_reminders(app))

        assert app.bot.send_message.await_count == 2

    def test_does_not_send_outside_reminder_hours(self):
        today = now_local().date()
        event = self._make_event("evt1", "Consulta")
        app = self._make_app()
        other_hour = (now_local().hour + 2) % 24

        with self._patch_agent(self._only_on(today, [event]), [other_hour]):
            asyncio.run(check_reminders(app))

        assert app.bot.send_message.await_count == 0

    def test_consulta_somente_as_datas_de_hoje_e_amanha(self):
        # Regressão: a busca usava janelas de 24h/48h a partir de agora, então
        # às 20h a faixa "amanhã" ia até as 20h de depois de amanhã.
        today = now_local().date()
        buscar = MagicMock(return_value=[])

        with self._patch_agent(buscar, [now_local().hour]):
            asyncio.run(check_reminders(self._make_app()))

        datas_consultadas = [chamada.args[1] for chamada in buscar.call_args_list]
        assert datas_consultadas == [today, today + timedelta(days=1)]

    def test_nao_anuncia_evento_de_depois_de_amanha(self):
        # Caso real: em 29/07 às 20h o bot anunciou como "Eventos de amanhã"
        # um compromisso que começava em 31/07.
        today = now_local().date()
        evento = self._make_event(
            "evt", "Caponga", start=now_local() + timedelta(days=2)
        )
        app = self._make_app()

        with self._patch_agent(
            self._only_on(today + timedelta(days=2), [evento]), [now_local().hour]
        ):
            asyncio.run(check_reminders(app))

        assert app.bot.send_message.await_count == 0

    def test_evento_de_varios_dias_nao_sai_em_hoje_e_amanha(self):
        # Um compromisso que atravessa os dois dias cai nas duas buscas;
        # repetido nas duas mensagens, parece erro para quem lê.
        longo = self._make_event("cap", "Caponga", start=now_local() + timedelta(hours=2))
        longo["end"] = {"dateTime": (now_local() + timedelta(days=2)).isoformat()}
        app = self._make_app()

        with self._patch_agent(MagicMock(return_value=[longo]), [now_local().hour]):
            asyncio.run(check_reminders(app))

        assert app.bot.send_message.await_count == 1
        assert "hoje" in app.bot.send_message.await_args.kwargs["text"].lower()

    def test_nao_lembra_evento_que_ja_terminou(self):
        # O lembrete das 20h buscava o dia inteiro e traria a consulta da manhã.
        today = now_local().date()
        encerrado = self._make_event(
            "evt", "Já passou", start=now_local() - timedelta(hours=3)
        )
        app = self._make_app()

        with self._patch_agent(self._only_on(today, [encerrado]), [now_local().hour]):
            asyncio.run(check_reminders(app))

        assert app.bot.send_message.await_count == 0


FORTALEZA = ZoneInfo("America/Fortaleza")


class TestNotificationKeyUsesLocalDate:
    def test_key_has_local_date_not_system_clock(self):
        # 22:00 em Fortaleza ainda é dia 13, mesmo que em UTC já seja dia 14.
        local_now = datetime(2026, 7, 13, 22, 0, tzinfo=FORTALEZA)
        with patch("src.agent.now_local", return_value=local_now):
            key = notification_key("daily", "matheus", 7)
        assert "2026-07-13" in key


class TestCheckDailySummaryTiming:
    # Regressão do bug principal: o disparo é decidido pelo horário local,
    # não pelo relógio do sistema (UTC dentro do container Docker).

    def setup_method(self):
        sent_notifications.clear()

    def _make_app(self):
        app = MagicMock()
        app.bot = MagicMock()
        app.bot.send_message = AsyncMock()
        return app

    def test_runs_at_local_summary_hour(self):
        local_now = datetime(2026, 7, 13, DAILY_SUMMARY_HOUR, 30, tzinfo=FORTALEZA)
        with patch("src.agent.now_local", return_value=local_now), \
                patch("src.agent.load_users", return_value={}) as mock_load:
            asyncio.run(check_daily_summary(self._make_app()))
        mock_load.assert_called_once()

    def test_does_not_run_when_utc_matches_but_local_does_not(self):
        # 04:00 em Fortaleza = 07:00 UTC. No bug antigo (relógio do container
        # em UTC) o resumo das 7h disparava aqui, de madrugada. Agora não.
        local_now = datetime(2026, 7, 13, 4, 0, tzinfo=FORTALEZA)
        with patch("src.agent.now_local", return_value=local_now), \
                patch("src.agent.load_users", return_value={}) as mock_load:
            asyncio.run(check_daily_summary(self._make_app()))
        mock_load.assert_not_called()


class TestCheckCoupleConflicts:
    # Regressão: as agendas do casal são compartilhadas, então o evento de um
    # aparece também na lista do outro e era sinalizado como conflito consigo
    # mesmo — acusava conflito havendo um único compromisso.

    def setup_method(self):
        sent_notifications.clear()

    def _make_app(self):
        app = MagicMock()
        app.bot = MagicMock()
        app.bot.send_message = AsyncMock()
        return app

    def _event(self, event_id: str, summary: str, hour: int, calendar_name: str | None = None) -> dict:
        start = datetime(2026, 7, 14, hour, 0, tzinfo=FORTALEZA)
        end = start + timedelta(hours=1)
        event = {
            "id": event_id,
            "summary": summary,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        if calendar_name:
            event["_calendar_name"] = calendar_name
        return event

    def _run(self, events_by_user: dict):
        app = self._make_app()
        local_now = datetime(2026, 7, 14, DAILY_SUMMARY_HOUR, 0, tzinfo=FORTALEZA)

        def fake_events(user_id, check_date):
            if check_date != local_now.date():
                return []
            return events_by_user.get(user_id, [])

        with patch.multiple(
            "src.agent",
            now_local=MagicMock(return_value=local_now),
            load_users=MagicMock(return_value={
                "1": {"name": "matheus"},
                "2": {"name": "cecilia"},
            }),
            is_user_authenticated=MagicMock(return_value=True),
            is_user_silenced=MagicMock(return_value=False),
            get_events_for_date=MagicMock(side_effect=fake_events),
        ):
            asyncio.run(check_couple_conflicts(app))
        return app

    def _sent_text(self, app) -> str:
        return app.bot.send_message.await_args.kwargs["text"]

    def test_does_not_flag_same_event_seen_in_both_calendars(self):
        event = self._event("evt1", "Consulta", 14)
        app = self._run({"matheus": [event], "cecilia": [event]})
        assert app.bot.send_message.await_count == 0

    def test_does_not_flag_identical_event_with_different_ids(self):
        # Cópias do mesmo compromisso podem ter ids diferentes; título e
        # horário iguais bastam para tratar como o mesmo evento.
        app = self._run({
            "matheus": [self._event("evt-a", "Consulta", 14)],
            "cecilia": [self._event("evt-b", "Consulta", 14)],
        })
        assert app.bot.send_message.await_count == 0

    def test_does_not_flag_events_from_familia_calendar(self):
        app = self._run({
            "matheus": [self._event("evt-fam", "Almoço", 12, calendar_name="Família")],
            "cecilia": [self._event("evt-x", "Reunião", 12)],
        })
        assert app.bot.send_message.await_count == 0

    def test_flags_genuine_conflict_between_different_events(self):
        app = self._run({
            "matheus": [self._event("evt-a", "Dentista", 14)],
            "cecilia": [self._event("evt-b", "Reunião", 14)],
        })
        assert app.bot.send_message.await_count == 2
        text = self._sent_text(app)
        assert "Dentista" in text
        assert "Reunião" in text

    def test_reports_mirrored_conflict_only_once(self):
        # Com agendas compartilhadas as duas listas trazem os dois eventos.
        dentista = self._event("evt-a", "Dentista", 14)
        reuniao = self._event("evt-b", "Reunião", 14)
        app = self._run({
            "matheus": [dentista, reuniao],
            "cecilia": [dentista, reuniao],
        })
        text = self._sent_text(app)
        assert text.count("Dentista") == 1


AGORA = datetime(2026, 7, 24, 9, 0, tzinfo=FORTALEZA)


class _BaseAvisoEventoNovo:
    """Infraestrutura compartilhada pelos testes de aviso de evento novo."""

    def setup_method(self):
        announced_new_events.clear()

    def _make_app(self):
        app = MagicMock()
        app.bot = MagicMock()
        app.bot.send_message = AsyncMock()
        return app

    def _event(self, event_id: str, summary: str, created_at: datetime) -> dict:
        start = datetime(2026, 7, 24, 19, 0, tzinfo=FORTALEZA)
        return {
            "id": event_id,
            "summary": summary,
            # Formato que o Google devolve (UTC com sufixo Z)
            "created": created_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        }

    def _run(
        self,
        events: list[dict],
        baseline: datetime | None,
        silenced: bool = False,
        marco_salvo: datetime | None = None,
        falha_na_busca: bool = False,
    ):
        """Roda um ciclo. `marco_salvo` simula o que estava gravado em disco."""
        app = self._make_app()
        self.salvar_marco = MagicMock()
        buscar_eventos = (
            MagicMock(side_effect=RuntimeError("API fora do ar"))
            if falha_na_busca
            else MagicMock(return_value=events)
        )
        with patch.multiple(
            "src.agent",
            new_events_since=baseline,
            now_local=MagicMock(return_value=AGORA),
            load_users=MagicMock(return_value={
                "1": {"name": "matheus"},
                "2": {"name": "cecilia"},
            }),
            is_user_authenticated=MagicMock(return_value=True),
            is_user_silenced=MagicMock(return_value=silenced),
            get_events=buscar_eventos,
            _load_new_events_marker=MagicMock(return_value=marco_salvo),
            _save_new_events_marker=self.salvar_marco,
        ):
            asyncio.run(check_new_events(app))
        return app


class TestCheckNewEvents(_BaseAvisoEventoNovo):
    # Os lembretes de horário fixo não cobrem o que é criado no meio do dia:
    # um evento marcado às 9h para as 19h não gerava aviso nenhum.

    def test_first_cycle_does_not_announce_existing_events(self):
        # Protege contra enxurrada de avisos a cada deploy/reinício.
        event = self._event("e1", "Sair", AGORA)
        app = self._run([event], baseline=None)
        assert app.bot.send_message.await_count == 0

    def test_announces_event_created_during_the_day_to_both(self):
        # Cenário real: marcado às 9h um compromisso para as 19h.
        event = self._event("e1", "Sair", AGORA - timedelta(minutes=5))
        app = self._run([event], baseline=AGORA - timedelta(minutes=15))

        assert app.bot.send_message.await_count == 2
        text = app.bot.send_message.await_args.kwargs["text"]
        assert "Novo compromisso" in text
        assert "Sair" in text

    def test_does_not_announce_the_same_event_twice(self):
        event = self._event("e1", "Sair", AGORA - timedelta(minutes=5))
        baseline = AGORA - timedelta(minutes=15)

        self._run([event], baseline=baseline)
        app = self._run([event], baseline=baseline)

        assert app.bot.send_message.await_count == 0

    def test_ignores_event_created_before_the_baseline(self):
        event = self._event("e1", "Compromisso antigo", AGORA - timedelta(days=2))
        app = self._run([event], baseline=AGORA - timedelta(minutes=15))
        assert app.bot.send_message.await_count == 0

    def test_does_not_announce_to_silenced_user(self):
        event = self._event("e1", "Sair", AGORA - timedelta(minutes=5))
        app = self._run([event], baseline=AGORA - timedelta(minutes=15), silenced=True)
        assert app.bot.send_message.await_count == 0

    def test_shows_who_added_the_event(self):
        event = self._event("e1", "Sair", AGORA - timedelta(minutes=5))
        event["creator"] = {"displayName": "Matheus Norjosa"}
        app = self._run([event], baseline=AGORA - timedelta(minutes=15))

        text = app.bot.send_message.await_args.kwargs["text"]
        assert "Matheus Norjosa" in text


class TestMarcoPersistido(_BaseAvisoEventoNovo):
    # Regressão: o marco vivia só em memória, então todo deploy criava uma
    # janela cega — evento criado antes do restart nunca era anunciado.

    def test_recupera_evento_criado_enquanto_o_bot_estava_fora(self):
        # Bot caiu às 8h30 e voltou às 9h; evento criado 8h50, durante a parada.
        evento = self._event("e1", "Sair", AGORA - timedelta(minutes=10))
        app = self._run(
            [evento],
            baseline=None,
            marco_salvo=AGORA - timedelta(minutes=30),
        )
        assert app.bot.send_message.await_count == 2

    def test_primeira_execucao_sem_estado_nao_anuncia_e_grava_o_marco(self):
        evento = self._event("e1", "Antigo", AGORA - timedelta(hours=2))
        app = self._run([evento], baseline=None, marco_salvo=None)

        assert app.bot.send_message.await_count == 0
        self.salvar_marco.assert_called_once_with(AGORA)

    def test_nao_despeja_o_acumulado_depois_de_parada_longa(self):
        # Marco de 5 dias atrás: só recupera a janela de 24h, não tudo.
        antigo = self._event("e1", "De 3 dias atrás", AGORA - timedelta(days=3))
        recente = self._event("e2", "De 1 hora atrás", AGORA - timedelta(hours=1))
        app = self._run(
            [antigo, recente],
            baseline=None,
            marco_salvo=AGORA - timedelta(days=5),
        )

        assert app.bot.send_message.await_count == 2
        textos = " ".join(c.kwargs["text"] for c in app.bot.send_message.await_args_list)
        assert "De 1 hora atrás" in textos
        assert "De 3 dias atrás" not in textos

    def test_avanca_o_marco_apos_ciclo_bem_sucedido(self):
        evento = self._event("e1", "Sair", AGORA - timedelta(minutes=5))
        self._run([evento], baseline=AGORA - timedelta(minutes=15))
        self.salvar_marco.assert_called_once_with(AGORA)

    def test_nao_avanca_o_marco_quando_a_busca_falha(self):
        # Avançar aqui faria os eventos daquele usuário serem pulados para sempre.
        self._run([], baseline=AGORA - timedelta(minutes=15), falha_na_busca=True)
        self.salvar_marco.assert_not_called()
