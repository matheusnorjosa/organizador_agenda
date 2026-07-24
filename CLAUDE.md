## Este projeto

Bot que liga o Google Calendar ao Telegram para um casal (Matheus e Cecília), rodando em
container Docker numa VM Oracle. Arquitetura, domínio e decisões: **`docs/arquitetura.md`**.

**Regra que mais causou bug aqui:** o container roda com relógio em **UTC** e os usuários
estão em **Fortaleza (UTC−3)**. Nunca use `datetime.now()` ou `date.today()` sem fuso para
decidir horário ou data — use `now_local()` (`src/calendar_api.py`). O resumo diário das 7h
já disparou às 4h da manhã por causa disso.

Skills do projeto (em `.claude/skills/`), carregar conforme a tarefa:
- `fuso-horario` — qualquer coisa com data, hora, lembrete ou agendamento
- `notificacoes` — mexer no laço de avisos (`src/agent.py`)
- `deploy` — publicar em produção (o deploy **não** dispara sozinho após o merge)

Agentes disponíveis: `revisor-agenda` (revisa contra as armadilhas conhecidas) e
`simulador-notificacao` (executa um cenário e mostra a mensagem que o bot enviaria).

## Git Workflow
- Do not include "Claude Code" in commit messages
- Use conventional commits (be brief and descriptive)
- Commit messages should explain what was changed and why

## Important Concepts
Focus on these principles in all code:
- error monitoring/observability
- automated tests
- readability/maintainability

## Coding Guidelines (Python)
- Use type hints where they add clarity
- Prefer async/await for I/O operations
- Unused variables should not exist. Prefix with `_` if necessary
- Avoid abbreviations. Names should be descriptive
- Use early returns instead of long if-else chains
- Follow conventions: SNAKE_CAPS for constants, snake_case for variables and functions

## Software Engineering
- No premature optimization. Optimize only when performance is measured
- Prioritize observability and security. These are not optional
- Comments should explain why, not what

## Testing
- Test behavior, not implementation details
- Every bug fix must be accompanied by a regression test
- Test names should describe outcomes: "returns_error_when_unauthorized"
- Rodar: `TIMEZONE=America/Fortaleza .venv/Scripts/python.exe -m pytest -q`
- Rodar também com `TZ=UTC` (cenário do servidor e do CI): a máquina de desenvolvimento
  está em UTC−3, então bug de fuso fica invisível nela
- Datas em teste devem vir de `now_local()`, nunca de `datetime.now()` — senão o teste só
  quebra na janela 00h–03h UTC (falha intermitente, já aconteceu duas vezes)

## Writing
- Be concise. Do not waste the reader's time
- Prefer active voice
- Keep sentences short. One idea per sentence
- Lead with the result, then explain supporting details
