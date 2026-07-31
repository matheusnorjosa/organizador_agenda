---
name: deploy
description: Como publicar uma mudança em produção neste projeto (VM Oracle/Docker). Use ao fazer commit, abrir PR ou quando o usuário pedir para colocar algo no ar. Contém a pegadinha do deploy que não dispara sozinho.
---

# Publicar em produção

Produção = **container Docker numa VM Oracle**, atualizado por GitHub Actions.

## A pegadinha principal

Se o auto-merge usa o `GITHUB_TOKEN`, o GitHub **não dispara workflows a partir de commits feitos por esse token** (proteção contra loops). Logo o `deploy.yml` **não roda sozinho depois do merge** — e a branch também não é apagada.

Sintoma: o PR aparece mergeado, tudo verde, e o bot continua rodando a versão antiga.

**Como saber em qual cenário você está:**

```bash
gh secret list | grep AUTO_MERGE_PAT
```

| Resultado | Comportamento |
|---|---|
| Secret existe | Deploy dispara sozinho (se o PR mexeu em `src/`, `requirements.txt` ou `Dockerfile`) e a branch some sozinha |
| Secret não existe | Cai no `GITHUB_TOKEN`: **disparar à mão** e apagar a branch à mão |

```bash
gh workflow run deploy.yml                 # publicar
git push origin --delete <branch>          # limpar
```

Na dúvida, **confirme que o deploy rodou depois do merge** em vez de supor:

```bash
gh run list --workflow=deploy.yml --limit 1
```

## "Success" não garante que o código subiu

Em 2026-07-30 descobrimos que a produção estava **6 dias parada** enquanto três deploys seguidos reportavam `success`. O `git pull` na VM abortava (`Your local changes would be overwritten`) porque o `deploy.sh` tinha sido editado lá, e o script continuava: o `docker build` reaproveitava o cache e recriava o container com o **código antigo**.

O script agora usa `set -euo pipefail` + `git fetch && git reset --hard origin/main` e verifica se o container ficou de pé. Mas a lição vale para qualquer suspeita de "corrigi e continua errado":

```bash
gh run view <run-id> --log | grep -iE "Updating|Fast-forward|error:|Aborting|COPY src"
```

- `Fast-forward` ou `Updating a..b` sem erro = código novo entrou
- `Aborting` = **não entrou**, mesmo com o job verde
- `COPY src/ src/ ---> Using cache` = o código-fonte não mudou nessa build

Se o usuário disser que a correção não surtiu efeito, **cheque isto antes de duvidar do código**.

Ligar o modo automático: `docs/setup_pat.md`.

## Fluxo completo

```bash
# 1. Branch SEMPRE da main atualizada (nunca de branch antiga)
git fetch origin main && git checkout -b <tipo>/<descricao> origin/main

# 2. Antes de codar: conferir se a main já resolveu isso
git log origin/main --oneline -10

# 3. Trabalho + testes
TIMEZONE=America/Fortaleza .venv/Scripts/python.exe -m pytest -q

# 4. Commit e PR (auto-merge cuida do merge quando os testes passam)
git push -u origin <branch>
gh pr create --base main --title "..." --body "..."

# 5. Confirmar o merge
gh pr view <n> --json state -q .state

# 6. Deploy — só necessário se o AUTO_MERGE_PAT não estiver configurado
gh workflow run deploy.yml

# 7. Confirmar que subiu (sempre confira, não suponha)
gh run list --workflow=deploy.yml --limit 1
```

O deploy faz SSH na VM → `git pull` + `docker build` + restart do container. Leva ~25s a 1min.

## Quando NÃO precisa deployar

O `Dockerfile` copia apenas `src/` e `requirements.txt`. Mudança somente em `docs/`, `tests/`, `.claude/`, `README` ou workflows **não afeta o container** — não dispare deploy à toa.

## Notas

- Branches são apagadas automaticamente no merge (`delete_branch_on_merge` ativo).
- Commits em pt-BR, conventional commits, sem mencionar ferramenta de IA (ver `CLAUDE.md`).
- O `.env` da VM é separado do local. Mudança de variável de ambiente exige editar lá por SSH — não vem no deploy.
