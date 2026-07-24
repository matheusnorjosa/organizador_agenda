---
name: deploy
description: Como publicar uma mudança em produção neste projeto (VM Oracle/Docker). Use ao fazer commit, abrir PR ou quando o usuário pedir para colocar algo no ar. Contém a pegadinha do deploy que não dispara sozinho.
---

# Publicar em produção

Produção = **container Docker numa VM Oracle**, atualizado por GitHub Actions.

## A pegadinha principal

O auto-merge usa `GITHUB_TOKEN`, e o GitHub **não dispara workflows a partir de commits feitos por esse token** (proteção contra loops). Logo o `deploy.yml` (`on: push` na main) **não roda sozinho depois do merge**.

Sintoma: o PR aparece mergeado, tudo verde, e o bot continua rodando a versão antiga. Já aconteceu — o último deploy automático foi meses antes de alguém notar.

**Sempre disparar à mão depois do merge:**

```bash
gh workflow run deploy.yml
```

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

# 6. Deploy (o passo que não é automático)
gh workflow run deploy.yml

# 7. Confirmar que subiu
gh run list --workflow=deploy.yml --limit 1
```

O deploy faz SSH na VM → `git pull` + `docker build` + restart do container. Leva ~25s a 1min.

## Quando NÃO precisa deployar

O `Dockerfile` copia apenas `src/` e `requirements.txt`. Mudança somente em `docs/`, `tests/`, `.claude/`, `README` ou workflows **não afeta o container** — não dispare deploy à toa.

## Notas

- Branches são apagadas automaticamente no merge (`delete_branch_on_merge` ativo).
- Commits em pt-BR, conventional commits, sem mencionar ferramenta de IA (ver `CLAUDE.md`).
- O `.env` da VM é separado do local. Mudança de variável de ambiente exige editar lá por SSH — não vem no deploy.
