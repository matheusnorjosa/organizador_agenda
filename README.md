# Organizador de Agenda

Agente Python que conecta Google Calendar ao Telegram para:
- Enviar lembretes automáticos (1 dia antes e no dia do evento)
- Criar eventos na agenda direto pelo Telegram

## Requisitos

- Python 3.10+
- Conta Google com Google Calendar
- Bot do Telegram

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

1. Crie o bot no Telegram (veja `docs/setup_telegram.md`)
2. Configure a API do Google Calendar (veja `docs/setup_google.md`)
3. Preencha o arquivo `.env` com seus tokens

## Como rodar

```bash
python -m src.agent
```

## Comandos do Telegram

| Comando | Descrição |
|---------|-----------|
| `/eventos` | Lista os próximos eventos da agenda |
| `/criar <título> <dd/mm/aaaa> <hh:mm>` | Cria um novo evento |
| `/ajuda` | Mostra os comandos disponíveis |
