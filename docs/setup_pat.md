# Deploy automático: criar o PAT do auto-merge

Guia para ligar o deploy automático e a exclusão automática de branch. Leva ~3 minutos.

## Validade do token atual

| Renovado em | Expira em | Prazo escolhido |
|---|---|---|
| 24/08/2026 | **22/11/2026** | 90 dias |

Para renovar, gere outro token com as permissões da seção abaixo e rode:

```bash
gh secret set AUTO_MERGE_PAT
```

### Dois modos de falha, sintomas opostos

Vale distinguir, porque o diagnóstico muda:

| Situação | O que acontece | Sintoma |
|---|---|---|
| Secret **ausente** ou vazio | A expressão `secrets.AUTO_MERGE_PAT \|\| secrets.GITHUB_TOKEN` cai no `GITHUB_TOKEN` | Job **verde**. Deploy não dispara e a branch não é apagada |
| Secret **presente**, token expirado ou sem permissão | Um token expirado ainda é uma string não vazia, então a expressão o escolhe. A API recusa a chamada | Job `auto-merge` **vermelho** no PR |

Ou seja: se o auto-merge falhou, olhe o token. Se ele passou mas o deploy não
rodou e a branch ficou, olhe se o secret existe.

Para saber qual token mergeou um PR, veja quem ativou o auto-merge:

```bash
gh pr view <n> --json autoMergeRequest -q .autoMergeRequest.enabledBy.login
```

Seu usuário = o PAT funcionou. `github-actions[bot]` = caiu no `GITHUB_TOKEN`.

## Por que isso é necessário

O auto-merge usa o `GITHUB_TOKEN`, um token temporário que o próprio GitHub Actions cria. Por segurança, o GitHub **não encadeia workflows a partir de ações feitas com esse token** — é uma proteção contra loops infinitos (um workflow que dispara outro que dispara o primeiro...).

Efeito colateral nos nossos dois casos:

| Sintoma | Por quê |
|---|---|
| O deploy não roda depois do merge | O push na `main` foi feito pelo `GITHUB_TOKEN` |
| A branch não é apagada depois do merge | Mesma coisa |

Usando um **PAT** (Personal Access Token — token pessoal seu), o merge passa a ser uma ação sua, e o GitHub encadeia normalmente.

## Passo a passo

### 1. Criar o token

1. Acesse **https://github.com/settings/personal-access-tokens/new** (Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token)
2. **Token name:** `organizador-agenda-automerge`
3. **Expiration:** escolha o prazo (ex.: 1 ano). ⚠️ Anote a data na seção "Validade do token atual" no topo deste arquivo — quando expirar, o job `auto-merge` passa a falhar nos PRs até você gerar outro.
4. **Repository access:** marque `Only select repositories` e escolha **`organizador_agenda`**
5. Em **Repository permissions**, ajuste apenas estas duas:
   - **Contents** → `Read and write`
   - **Pull requests** → `Read and write`
6. Clique em **Generate token** e **copie o valor** (ele só aparece uma vez)

> Use o token *fine-grained*, não o clássico: ele fica restrito a este repositório e a essas duas permissões. Um token clássico com escopo `repo` também funciona, mas dá acesso a todos os seus repositórios — é mais poder do que o necessário.

### 2. Cadastrar como secret do repositório

1. Acesse **https://github.com/matheusnorjosa/organizador_agenda/settings/secrets/actions**
2. **New repository secret**
3. **Name:** `AUTO_MERGE_PAT` (exatamente assim)
4. **Secret:** cole o token
5. **Add secret**

### 3. Conferir

Abra o próximo PR normalmente. Se deu certo:

- O deploy roda **sozinho** após o merge (quando o PR mexe em `src/`, `requirements.txt` ou `Dockerfile`)
- A branch é **apagada sozinha**

Se não funcionar, o workflow continua caindo no `GITHUB_TOKEN` — nada quebra, só permanece o comportamento manual de hoje.

## O que acontece se eu não fizer

Nada quebra. O `auto-merge.yml` usa `secrets.AUTO_MERGE_PAT || secrets.GITHUB_TOKEN`: sem o secret, ele cai no comportamento atual. A diferença é que continua sendo preciso, após cada merge que mexe em código:

```bash
gh workflow run deploy.yml                          # publicar
git push origin --delete <branch>                   # limpar a branch
```

## Segurança

- O token fica guardado como secret do repositório: o GitHub não o exibe depois de salvo e mascara o valor nos logs.
- As permissões são as mínimas necessárias (conteúdo e PRs, só neste repositório).
- Para revogar a qualquer momento: **Settings → Developer settings → Personal access tokens** → apagar o token. O workflow volta sozinho ao `GITHUB_TOKEN`.
