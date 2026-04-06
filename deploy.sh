#!/bin/bash
set -e

cd ~/organizador_agenda

echo "📥 Atualizando código..."
git pull

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
  organizador-agenda

echo "✅ Bot atualizado e rodando!"
docker logs --tail 5 organizador-agenda
