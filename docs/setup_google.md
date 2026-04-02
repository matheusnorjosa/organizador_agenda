# Como configurar a API do Google Calendar

## Passo 1 — Criar projeto no Google Cloud

1. Acesse https://console.cloud.google.com/
2. Clique em **Selecionar projeto** > **Novo projeto**
3. Dê um nome (ex: Organizador Agenda) e clique em **Criar**

## Passo 2 — Habilitar a API do Google Calendar

1. No menu lateral, vá em **APIs e serviços** > **Biblioteca**
2. Pesquise por **Google Calendar API**
3. Clique nela e depois em **Ativar**

## Passo 3 — Criar credenciais OAuth

1. Vá em **APIs e serviços** > **Credenciais**
2. Clique em **Criar credenciais** > **ID do cliente OAuth**
3. Se pedir para configurar a tela de consentimento:
   - Escolha **Externo**
   - Preencha o nome do app e seu email
   - Em **Escopos**, pode pular
   - Em **Usuários de teste**, adicione seu email do Gmail
   - Salve
4. Volte em **Credenciais** > **Criar credenciais** > **ID do cliente OAuth**
5. Tipo de aplicativo: **App para computador**
6. Dê um nome e clique em **Criar**
7. Clique em **Fazer download do JSON**
8. Renomeie o arquivo para `credentials.json` e coloque na raiz do projeto (`E:\organizador_agenda\credentials.json`)

## Passo 4 — Primeira autenticação

Ao rodar o projeto pela primeira vez (`python -m src.agent`), uma janela do navegador vai abrir pedindo para autorizar o acesso ao seu Google Calendar. Autorize e o arquivo `token.json` será criado automaticamente.

## Resultado

Você deve ter na raiz do projeto:
- `credentials.json` (baixado do Google Cloud)
- `token.json` (criado automaticamente após a primeira autorização)
