# Como criar o Bot no Telegram

## Passo 1 — Criar o bot

1. Abra o Telegram e procure por **@BotFather**
2. Envie o comando `/newbot`
3. Escolha um **nome** para o bot (ex: Minha Agenda)
4. Escolha um **username** para o bot (deve terminar com `bot`, ex: `minha_agenda_bot`)
5. O BotFather vai te enviar um **token**. Copie esse token.
6. Cole o token no arquivo `.env` na variável `TELEGRAM_BOT_TOKEN`

## Passo 2 — Descobrir seu Chat ID

1. Abra o Telegram e procure por **@userinfobot**
2. Envie qualquer mensagem para ele
3. Ele vai responder com seu **ID** (um número)
4. Cole esse número no arquivo `.env` na variável `TELEGRAM_CHAT_ID`

## Resultado

Seu `.env` deve ficar assim:

```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321
```

## Trocar o token (se ele vazar)

Quem tem o token controla o bot. Se ele aparecer onde não devia (log, print, commit), troque:

1. No **@BotFather**: `/mybots` → escolha o bot → **API Token** → **Revoke current token**. O token antigo para de funcionar na hora, e o bot fica fora do ar até o passo 3.
2. Na VM, troque o valor de `TELEGRAM_BOT_TOKEN` no `.env` da pasta `~/organizador_agenda`. Troque também no `.env` local, se você roda o bot na sua máquina.
3. Recrie o container para ele ler o `.env` novo: `gh workflow run deploy.yml`. Reiniciar não basta, porque o `docker run` só lê o `--env-file` quando cria o container.
4. Confira:
   - o token novo responde `"ok": true` em `https://api.telegram.org/bot<token>/getMe`, e o antigo dá 401;
   - o log do deploy não mostra o token (`grep -c "api.telegram.org/bot[0-9]"` dá 0);
   - o bot responde a um `/status`.

Para quem usa o bot, nada muda: nome, conversa e histórico continuam, e ninguém precisa refazer `/start` nem `/auth`.

Feito em 2026-09-23, depois de o token aparecer em logs públicos de deploy (ver "Logs e segredos" em `docs/arquitetura.md`).
