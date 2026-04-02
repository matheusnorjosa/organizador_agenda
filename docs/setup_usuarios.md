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

## Passo 3 — Autenticar a conta Google da pessoa

Rode o script de autenticação:

```bash
python -m src.auth cecilia
```

Uma janela do navegador vai abrir. A pessoa precisa fazer login na conta Google **dela** e autorizar o acesso ao Calendar. O token será salvo em `tokens/cecilia.json`.

## Pronto

A pessoa já pode mandar comandos para o bot no Telegram e vai receber lembretes da agenda dela.
