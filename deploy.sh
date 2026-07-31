#!/bin/bash
set -e

cd ~/organizador_agenda

echo "📥 Atualizando código..."
# git pull aborta se algum arquivo foi alterado na VM. O deploy espelha a
# main; o que é local (.env, tokens/, users.json, estado/) é gitignored e
# não é afetado pelo reset.
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  Alterações locais serão descartadas:"
  git status --short
fi
git fetch origin main
git reset --hard origin/main
echo "   commit: $(git rev-parse --short HEAD)"

echo "🛑 Parando bot anterior..."
docker stop organizador-agenda 2>/dev/null && docker rm organizador-agenda 2>/dev/null || true

echo "🔨 Construindo nova imagem..."
docker build -t organizador-agenda .

echo "🚀 Iniciando bot..."
docker run -d \
  --name organizador-agenda \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/credentials.json:/app/credentials.json \
  -v $(pwd)/tokens:/app/tokens \
  -v $(pwd)/users.json:/app/users.json \
  -v $(pwd)/estado:/app/estado \
  organizador-agenda

sleep 5
if [ -z "$(docker ps -q -f name=organizador-agenda -f status=running)" ]; then
  echo "❌ Container não está rodando após o deploy"
  docker logs --tail 30 organizador-agenda || true
  exit 1
fi

echo "✅ Bot atualizado e rodando!"
docker logs --tail 5 organizador-agenda
