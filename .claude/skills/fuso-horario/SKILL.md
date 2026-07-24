---
name: fuso-horario
description: Regras de data e hora deste projeto. Use SEMPRE que a tarefa tocar horário, data, notificação, agendamento, lembrete, "hoje"/"amanhã", ou formatação de evento. É a classe de bug mais recorrente aqui.
---

# Fuso horário

## O problema estrutural

O bot roda em **container Docker com relógio de sistema em UTC**. Os usuários estão em **Fortaleza (UTC−3, sem horário de verão)**.

Qualquer `datetime.now()` ou `date.today()` **sem fuso** retorna UTC e sai 3 horas deslocado. Não é hipótese: o resumo diário das 7h já disparou às 4h da manhã em produção por causa disso.

## A regra

```python
from src.calendar_api import now_local

agora = now_local()          # datetime com fuso (TIMEZONE)
hoje  = now_local().date()   # data local
```

Nunca use, para decidir horário ou data:

- ❌ `datetime.now()`
- ❌ `date.today()`
- ❌ `datetime.utcnow()` (além de tudo, deprecado)

Para converter um `dateTime` que veio do Google antes de exibir, use `_parse_event_datetime()` (`src/calendar_api.py`).

## Exceção legítima

Duração relativa pode usar relógio ingênuo, desde que **as duas pontas usem o mesmo**. É o caso de `is_user_silenced`/`set_silence`: "silenciar por 12h" é imune ao fuso. Não misture com `now_local()` no mesmo cálculo — comparar datetime com fuso e sem fuso levanta `TypeError`.

## Como testar de verdade

A máquina de desenvolvimento (Windows do usuário) já está em UTC−3, então **o bug fica invisível nela**. Rode simulando o servidor:

```bash
TZ=UTC TIMEZONE=America/Fortaleza .venv/Scripts/python.exe -m pytest -q
```

Nesse modo `datetime.now().hour` e `now_local().hour` divergem em 3 — exatamente produção e o runner do CI.

Nos testes, **derive datas de `now_local()`**, nunca de `datetime.now()`. Caso contrário o teste só quebra na janela 00h–03h UTC: falha intermitente, difícil de achar. Isso já aconteceu duas vezes neste repo.

## Checklist antes de fechar a tarefa

- [ ] Nenhum `datetime.now()` / `date.today()` novo (`grep -nE "datetime\.now\(\)|date\.today\(\)" src/`)
- [ ] Suíte passa também com `TZ=UTC`
- [ ] Testes novos derivam data de `now_local()`
- [ ] Se mudou produção para fuso local, os testes existentes que montavam data pelo relógio do sistema foram alinhados

## Se o horário ainda parecer errado

O problema pode não estar no código. Verifique a configuração de fuso **da própria agenda no Google Calendar** — a agenda `Família` já esteve em GMT+00:00, o que afeta evento de dia inteiro e recorrência.
