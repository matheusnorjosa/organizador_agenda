# Organizador de Agenda

Bot do Telegram que integra Google Calendar, Google Tasks e Google Contacts para gerenciamento completo da sua agenda pessoal — com lembretes automáticos, criação de eventos por linguagem natural via IA e suporte a múltiplos usuários.

## Funcionalidades

### Agenda
- Lembretes automáticos (1 dia antes e no dia)
- Aviso quando um compromisso novo é criado, informando quem adicionou
- Resumo diário às 7h com eventos separados por período (manhã, tarde, noite)
- Resumo semanal todo domingo com programação dia a dia
- Criar, editar e excluir eventos pelo Telegram
- Criar eventos por linguagem natural com IA (ex: "reunião sexta às 14h")
- Eventos recorrentes (diário, semanal, quinzenal, mensal)
- Seleção de agenda ao criar eventos (quando há múltiplas)
- Busca eventos de todas as agendas (próprias, compartilhadas e inscritas)
- Visualização de horários livres do dia

### Tarefas
- Listar, criar, concluir e excluir tarefas do Google Tasks
- Tarefas atrasadas destacadas com alerta visual
- Tarefas pendentes incluídas no resumo diário

### Casal
- Agenda compartilhada do casal lado a lado
- Detecção automática de conflitos de horário — ignora o mesmo evento visto nas duas
  agendas compartilhadas e os compromissos da agenda conjunta `Família`
- Criar evento nas agendas de todos os usuários

### Outros
- Aniversários da semana (via Google Contacts)
- Modo silencioso para pausar lembretes
- Auto-registro e autenticação via Telegram
- Monitoramento com `/status` (uptime, erros, notificações)
- Alertas de erro enviados ao administrador

## Tecnologias

- **Python 3.12** — Linguagem principal
- **python-telegram-bot** — Integração com Telegram
- **Google APIs** — Calendar, Tasks, People
- **Groq (Llama 3.3)** — Processamento de linguagem natural
- **Docker** — Containerização
- **GitHub Actions** — CI/CD (testes + deploy automático)
- **Oracle Cloud** — Hospedagem gratuita (Always Free VM)

## Arquitetura

```
src/
├── agent.py           # Loop principal: notificações e orquestração
├── calendar_api.py    # Integração com Google Calendar, Tasks e Contacts
├── telegram_bot.py    # Comandos e handlers do Telegram
├── natural_language.py # Interpretação de linguagem natural via IA
└── auth.py            # Script de autenticação local
```

Detalhes de arquitetura, regras de fuso horário, laço de notificações e o modelo de agendas
compartilhadas: [docs/arquitetura.md](docs/arquitetura.md).

## Comandos do Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Boas-vindas e introdução ao bot |
| `/auth` | Cadastra e conecta conta Google |
| `/hoje` | Eventos de hoje por período |
| `/amanha` | Eventos de amanhã |
| `/eventos` | Próximos 7 dias |
| `/agendar <texto>` | Cria evento por linguagem natural |
| `/criar <título> <data> <hora>` | Cria evento com formato fixo |
| `/criar_casal <título> <data> <hora>` | Cria nas agendas de todos |
| `/editar` | Edita título, data ou hora de um evento |
| `/excluir` | Exclui um evento (com confirmação) |
| `/livre` | Horários vagos de hoje |
| `/semana` | Programação da semana |
| `/semana_casal` | Agenda do casal lado a lado |
| `/aniversarios` | Aniversários dos próximos 7 dias |
| `/tarefas` | Lista tarefas pendentes |
| `/nova_tarefa <título> [data]` | Cria tarefa com prazo opcional |
| `/concluir` | Marca tarefa como concluída |
| `/excluir_tarefa` | Remove uma tarefa |
| `/status` | Saúde e estatísticas do bot |
| `/silencio <horas>` | Pausa lembretes |
| `/ativar` | Reativa lembretes |
| `/ajuda` | Lista todos os comandos |

## Instalação

### Requisitos
- Python 3.10+
- Conta Google com Calendar habilitado
- Bot do Telegram (via @BotFather)

### Setup

```bash
git clone https://github.com/matheusnorjosa/organizador_agenda.git
cd organizador_agenda
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### Configuração

1. Configure a API do Google Calendar — veja [docs/setup_google.md](docs/setup_google.md)
2. Crie o bot no Telegram — veja [docs/setup_telegram.md](docs/setup_telegram.md)
3. Adicione usuários — veja [docs/setup_usuarios.md](docs/setup_usuarios.md)
4. Crie o arquivo `.env` na raiz com as variáveis necessárias
5. (Opcional) Configure a API do Groq para linguagem natural

### Rodar

```bash
python -m src.agent
```

### Docker

```bash
docker build -t organizador-agenda .
docker run -d --name organizador-agenda --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/credentials.json:/app/credentials.json \
  -v $(pwd)/tokens:/app/tokens \
  -v $(pwd)/users.json:/app/users.json \
  organizador-agenda
```

## CI/CD

O projeto usa GitHub Actions com três workflows:

- **Testes** — Roda automaticamente em cada Pull Request para `main`
- **Auto-merge** — Faz merge (squash) do PR quando os testes passam
- **Deploy** — Atualiza o container na VM: `git pull` + rebuild + restart

> **Atenção:** o deploy **não** dispara sozinho depois do auto-merge. Merges feitos pelo
> `GITHUB_TOKEN` não acionam outros workflows (proteção do GitHub contra loops). Depois do
> merge, publique com:
> ```bash
> gh workflow run deploy.yml
> ```
> Mudança apenas em `docs/`, `tests/` ou `.claude/` não precisa de deploy — o `Dockerfile`
> só copia `src/`.

## Testes

```bash
pip install -r requirements-dev.txt
TIMEZONE=America/Fortaleza pytest tests/ -v
```

Rode também simulando o servidor, que roda em UTC — é onde bugs de fuso aparecem:

```bash
TZ=UTC TIMEZONE=America/Fortaleza pytest tests/ -q
```

## Licença

Projeto pessoal de uso privado.
