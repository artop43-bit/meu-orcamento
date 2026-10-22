#!/usr/bin/env bash
# Atualiza o servidor com a versão mais recente da main e reconstrói os contêineres.
# Chamado pelo GitHub Actions (workflow Deploy) ou à mão:  bash deploy/scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -f .env.production ]; then
  echo "Falta o arquivo .env.production (veja docs/DEPLOY.md)." >&2
  exit 1
fi

echo "==> $(date -Iseconds) atualizando código"
git fetch --quiet origin main
git reset --hard origin/main

echo "==> Construindo e subindo contêineres"
deploy/scripts/compose.sh up -d --build --remove-orphans

echo "==> Limpando imagens antigas"
docker image prune -f > /dev/null
# Cache de montagem com mais de 7 dias (v1.4.4): sem isso ele cresce a cada deploy.
docker builder prune -f --filter "until=168h" > /dev/null

deploy/scripts/compose.sh ps
echo "==> Deploy concluído: $(git log -1 --format='%h %s')"
