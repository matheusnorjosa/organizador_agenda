# Como adicionar novos usuários

## Passo 1 — Pegar o Telegram ID da pessoa

1. Peça para a pessoa abrir o Telegram e falar com o **@userinfobot**
2. Ele vai responder com o **ID** (um número)

## Passo 2 — Adicionar no users.json

Abra o arquivo `users.json` na raiz do projeto e adicione a pessoa:

```json
{
  "1255073381": {
    "name": "matheus"
  },
  "ID_DA_CECILIA": {
    "name": "cecilia"
  }
}
```

O `name` é usado para identificar o arquivo de token Google (`tokens/cecilia.json`).

## Passo 3 — Autenticar a conta Google

Existem duas formas:

### Opção A — Pelo Telegram (remoto)

1. A pessoa manda `/auth` para o bot no Telegram
2. O bot envia um link do Google
3. A pessoa clica, faz login na conta Google dela e autoriza
4. Será redirecionada para uma página que não carrega (normal!)
5. Copia a URL da barra de endereço e cola no chat do bot
6. Pronto!

### Opção B — Pelo terminal (local)

Se a pessoa estiver no mesmo computador:

```bash
python -m src.auth cecilia
```

Uma janela do navegador vai abrir para fazer login.

## Pronto

A pessoa já pode mandar comandos para o bot no Telegram e vai receber lembretes da agenda dela.
