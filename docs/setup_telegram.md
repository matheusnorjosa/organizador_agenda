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
