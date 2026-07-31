# Arquitetura

Referência técnica do bot. Para o passo a passo de configuração, ver `setup_google.md`, `setup_telegram.md` e `setup_usuarios.md`.

## Visão geral

Bot de agenda para um casal. Lê o Google Calendar (e o Google Tasks) de cada usuário e conversa por um bot do Telegram: envia notificações automáticas e aceita comandos, inclusive em linguagem natural.

Roda em **container Docker numa VM Oracle**. O processo é único e tem duas partes concorrentes:

- `Application.updater.start_polling()` — atende comandos do Telegram
- `notification_loop()` — laço que verifica a agenda e envia avisos

## Módulos

| Arquivo | Responsabilidade |
|---|---|
| `src/agent.py` | Ponto de entrada. Laço de notificações e todas as regras de "quando avisar". |
| `src/calendar_api.py` | Google Calendar, Tasks e People (contatos). Formatação de eventos e tarefas. Fonte do fuso. |
| `src/telegram_bot.py` | Handlers dos comandos e botões do Telegram. Cadastro de usuários (`users.json`). |
| `src/natural_language.py` | Interpreta texto livre via API da Groq (Llama) e devolve intenção/evento em JSON. |
| `src/auth.py` | Autenticação Google local (`python -m src.auth <nome>`). No dia a dia usa-se `/auth` no Telegram. |

Estado que não está no código: `tokens/` (credenciais OAuth por usuário) e `users.json` (mapa telegram_id → nome). Ambos fora do versionamento, montados como volume no container.

## Fuso horário — a regra mais importante

**O container roda com relógio em UTC e os usuários estão em Fortaleza (UTC−3).** Usar `datetime.now()` ou `date.today()` sem fuso faz tudo sair deslocado 3 horas. Isso já causou bug real em produção: o resumo diário das 7h disparava às 4h da manhã.

**Regra:** nunca decidir horário ou data pelo relógio do sistema.

```python
from src.calendar_api import now_local

agora = now_local()          # datetime com fuso, respeita TIMEZONE
hoje  = now_local().date()   # data local
```

Camadas de proteção já existentes:

| Camada | Como |
|---|---|
| Decisão de horário/data | `now_local()` em vez de `datetime.now()` |
| Leitura da API | `events().list(timeZone=...)` — o Google já devolve no fuso configurado |
| Exibição | `_parse_event_datetime()` converte antes de formatar (cinto e suspensório) |
| Escrita | `create_event`/`update_event` enviam `timeZone` explícito |
| Logs do container | `ENV TZ=America/Fortaleza` no `Dockerfile` |

O fuso vem de `TIMEZONE` no `.env`; o padrão no código é `America/Fortaleza`.

> Fora do código: a configuração de fuso **da própria agenda no Google** também importa para eventos de dia inteiro e recorrências. A agenda `Família` já esteve em GMT+00:00 — se aparecer horário estranho, conferir lá também.

## Laço de notificações

`notification_loop()` roda a cada `CHECK_INTERVAL_SECONDS` (15 min). Cada verificação decide sozinha se é a hora dela:

| Verificação | Quando dispara | O que envia |
|---|---|---|
| `check_new_events` | todo ciclo (15 min) | Aviso de compromisso recém-criado |
| `check_reminders` | 8h e 20h | Eventos de hoje / de amanhã |
| `check_daily_summary` | 7h | Resumo do dia + tarefas pendentes |
| `check_couple_conflicts` | 7h | Conflitos de horário entre os dois |
| `check_weekly_summary` | domingo 20h | Programação da semana + aniversários |

Não existe aviso de "evento começando em X minutos" — foi removido no PR #3 por gerar repetição.

**Lacuna conhecida:** os horários fixos não cobrem o meio do dia. Um evento criado às 9h para as 19h não entra em nenhuma janela (às 8h não existia; às 20h já passou). É exatamente o que o `check_new_events` cobre.

### Deduplicação

Sem controle, o laço reenviaria a mesma notificação a cada 15 minutos.

- **Notificações de horário:** chave `tipo:usuario:data:hora` em `sent_notifications`. `cleanup_old_keys()` remove as de dias anteriores (a data vem do fuso local).
- **Aviso de evento novo:** chave `new:usuario:evento_id` em `announced_new_events`.

### Detecção de "evento novo"

Três decisões de design que evitam falhas reais:

1. **Marco temporal persistido em disco** (`new_events_since`, em `estado/notificacoes.json`). O bot anuncia o que foi criado depois do marco e avança o marco a cada ciclo completo.

   Duas coisas dependem disso:
   - Na **primeira execução** (sem arquivo) o marco vira "agora" e nada é anunciado — senão todo deploy despejaria a agenda inteira no Telegram.
   - Em **reinícios seguintes** o marco vem do disco, então eventos criados enquanto o bot estava fora do ar são recuperados. Quando o marco vivia só em memória, cada deploy criava uma **janela cega**: um evento criado antes do restart nunca era anunciado.

   Depois de uma parada longa a recuperação é limitada a `MAX_RECOVERY_WINDOW` (24h), para não despejar dias de eventos de uma vez.

   O marco **não avança se a busca falhar** para algum usuário — avançar puliria aqueles eventos para sempre.

2. **Usa o campo `created` do evento, não a presença dele.** A busca olha 30 dias à frente (`NEW_EVENT_LOOKAHEAD_DAYS`); um compromisso marcado para daqui a 40 dias entraria nessa janela sozinho com o passar do tempo e seria anunciado como "novo" sem ninguém ter criado nada.

3. **Chave por evento/usuário** (`announced_new_events`, em memória) evita repetir o aviso dentro da mesma execução.

> **O diretório `estado/` precisa estar montado como volume.** O container é recriado a cada deploy; sem o volume o arquivo se perde e a persistência não serve para nada. Está declarado em `deploy.yml`, `deploy.sh` e `docker-compose.yml`.

## Modelo de domínio: agendas compartilhadas

O ponto que mais confunde neste projeto.

**As agendas dos dois são compartilhadas entre si.** `list_all_calendars()` devolve todas as agendas às quais o usuário tem acesso, então `get_events_for_date()` retorna praticamente **a mesma lista para os dois**. Consequências:

- Um evento criado por um aparece nos resumos e lembretes do outro **sem precisar estar em nenhuma agenda especial**.
- A lista devolvida para um usuário **não diz de quem é** cada evento. Tratar `get_events_for_date("matheus")` como "eventos do Matheus" é o erro que gerou duas rodadas de bug em conflitos.

### Quem é o dono de um evento

A pista está em `_calendar_name`, que `_fetch_events_from_all_calendars` só preenche para agendas **não primárias**:

| Como o evento aparece na lista de X | Significa |
|---|---|
| Sem `_calendar_name` | Está na agenda principal de X — é compromisso **de X** |
| `_calendar_name` = agenda conjunta (`Família`) | Compromisso **dos dois** |
| `_calendar_name` = outra agenda | Veio da agenda do parceiro ou de terceiro — dono indefinido, ignorado |

### Detecção de conflito

O modelo é: **cada evento prende um conjunto de pessoas**, e há conflito quando dois eventos sobrepostos prendem **alguém em comum** (`_commitment_map` + `_find_conflicts`).

| Situação | Vira conflito? |
|---|---|
| Dois compromissos da mesma pessoa | **Sim** — ninguém está em dois lugares |
| Compromisso conjunto × individual de um deles | **Sim** — alguém vai faltar ao conjunto |
| Cada um com o seu compromisso | Não — não há disputa |
| Mesmo evento visto nas duas agendas | Não — é um evento só (deduplicado por `id`) |
| Par já reportado em outro dia | Só uma vez |

A mensagem informa **quem** fica preso e a **janela de sobreposição**, não o horário de início solto: `• 31/07 15:00 às 16:00 — matheus: Dentista × Reunião`.

> Compromisso de agenda secundária (ex.: uma agenda "Trabalho" só do Matheus) não entra na checagem, porque não dá para atribuir dono com segurança. A escolha é conservadora de propósito: erra para menos ruído.

## Testes

`pytest`, sem rede: as chamadas ao Google e ao Telegram são mockadas.

```bash
TIMEZONE=America/Fortaleza .venv/Scripts/python.exe -m pytest -q
```

Duas convenções que vieram de bugs reais:

1. **Testar simulando o servidor.** A máquina de desenvolvimento está em UTC−3, então bug de fuso fica invisível nela. Rodar também com o relógio do sistema em UTC, que é o cenário de produção e do CI:
   ```bash
   TZ=UTC TIMEZONE=America/Fortaleza .venv/Scripts/python.exe -m pytest -q
   ```

2. **Derivar datas de `now_local()` nos testes**, nunca de `datetime.now()`. Teste que monta data pelo relógio do sistema enquanto o código usa fuso local só quebra na janela 00h–03h UTC — falha intermitente e difícil de diagnosticar.

Para provar que um teste de regressão realmente pega o bug, rodá-lo contra o código anterior (`git stash push -- src/arquivo.py`, rodar, `git stash pop`) e confirmar que falha.

## Deploy

Ver `.claude/skills/deploy/SKILL.md`. Resumo: PR → auto-merge (squash) → **disparar o deploy à mão** com `gh workflow run deploy.yml`, porque merges feitos pelo `GITHUB_TOKEN` não disparam workflows.

O `Dockerfile` copia apenas `src/` e `requirements.txt` — mudança só em `docs/`, `tests/` ou `.claude/` não exige deploy.
