# Plano de Implementação - Organizador de Agenda

## Visão Geral

Agente Python que conecta Google Calendar ao Telegram Bot para:
- **Lembrar** de eventos (1 dia antes e no dia)
- **Criar** eventos na agenda direto pelo Telegram

- **Linguagem:** Python
- **Execução:** Local (Windows 11)
- **Fluxo:**
  - Lembretes: Google Calendar API → Agente verifica eventos → Telegram Bot avisa
  - Criação: Telegram Bot recebe comando → Agente cria evento → Google Calendar API

---

## Etapa 1 — Configurações externas

1. **Criar bot no Telegram** — Falar com o @BotFather no Telegram, criar um bot e pegar o token
2. **Configurar Google Calendar API** — Criar um projeto no Google Cloud Console e habilitar a API do Calendar (leitura + escrita)

## Etapa 2 — Estrutura do projeto

3. Criar o `requirements.txt` com as dependências
4. Criar arquivo `.env` para guardar tokens e credenciais de forma segura

## Etapa 3 — Código

5. **Módulo Google Calendar** — Conecta na API, busca eventos e cria novos eventos
6. **Módulo Telegram** — Recebe comandos e envia mensagens via bot
7. **Agente principal** — Orquestra tudo: loop de lembretes + escuta comandos do Telegram

## Comandos do Telegram Bot

- `/eventos` — Lista os próximos eventos da agenda
- `/criar <título> <data> <hora>` — Cria um novo evento na agenda
- `/ajuda` — Mostra os comandos disponíveis

## Etapa 4 — Rodar

8. Testar tudo junto e deixar rodando na máquina
