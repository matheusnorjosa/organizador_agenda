---
name: notificacoes
description: Como funciona o laço de notificações e como adicionar ou alterar um aviso sem causar spam ou repetição. Use ao mexer em src/agent.py, lembretes, resumos ou avisos do bot.
---

# Laço de notificações

`notification_loop()` em `src/agent.py` roda a cada 15 min (`CHECK_INTERVAL_SECONDS`). Cada verificação decide sozinha se é a hora dela.

| Verificação | Quando | O que envia |
|---|---|---|
| `check_new_events` | todo ciclo | Compromisso recém-criado |
| `check_reminders` | 8h e 20h | Eventos de hoje / amanhã |
| `check_daily_summary` | 7h | Resumo do dia + tarefas |
| `check_couple_conflicts` | 7h | Conflitos entre os dois |
| `check_weekly_summary` | domingo 20h | Semana + aniversários |

## As três armadilhas

Toda notificação neste projeto já caiu em pelo menos uma delas.

### 1. Repetição a cada ciclo

O laço roda de 15 em 15 min. Sem controle, a mesma mensagem sai 4 vezes por hora.

Use as chaves de deduplicação:
- Notificação de horário: `notification_key(tipo, usuario, hora)` → `sent_notifications`
- Aviso por evento: `f"new:{usuario}:{evento_id}"` → `announced_new_events`

### 2. Enxurrada a cada deploy

Deploy reinicia o container e **zera o estado em memória**. Uma verificação do tipo "avise sobre o que apareceu" anunciaria a agenda inteira a cada deploy.

Solução usada em `check_new_events`: um marco temporal definido no **primeiro ciclo** (`new_events_since`). O que já existia quando o processo subiu não é novidade.

### 3. Falso positivo pela janela de busca

`check_new_events` olha 30 dias à frente. Se a detecção fosse por "o evento apareceu na lista", um compromisso marcado para daqui a 40 dias entraria na janela sozinho com o tempo e seria anunciado como novo — sem ninguém ter criado nada.

Por isso a detecção usa o campo **`created`** do evento, não a presença dele.

## Checklist para adicionar uma notificação

- [ ] Decide o horário com `now_local()`, nunca `datetime.now()` (ver skill `fuso-horario`)
- [ ] Tem chave de deduplicação — não repete no ciclo seguinte
- [ ] Não dispara enxurrada quando o processo reinicia
- [ ] Respeita `is_user_silenced(int(telegram_id))`
- [ ] Envia por `send_message()` (atualiza `bot_stats`)
- [ ] Erros em `try/except` com `logger.error` e `bot_stats["errors_count"]`
- [ ] Registrada em `notification_loop()`
- [ ] Testes cobrem: envia quando deve, **não** envia fora da hora, não repete, respeita silêncio

## Testar

Os testes mockam tudo (`patch.multiple("src.agent", ...)`) — sem rede. Padrão em `tests/test_agent.py`: mocke `now_local`, `load_users`, `is_user_authenticated`, `is_user_silenced` e a função de busca de eventos; depois inspecione `app.bot.send_message.await_count` e o `text`.

Para ver a mensagem real que o usuário receberia, rode um script com `PYTHONIOENCODING=utf-8` (o console do Windows quebra nos emoji).

## Lacuna conhecida

Não existe aviso de "evento começando em X minutos" — foi removido no PR #3 por repetir. Se for reimplementar, o sistema de chaves atual resolve o problema que causou a remoção.
