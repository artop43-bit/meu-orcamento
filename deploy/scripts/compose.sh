#!/usr/bin/env bash
# Atalho para o docker compose de produção. Ex.: deploy/scripts/compose.sh logs -f api
set -euo pipefail
cd "$(dirname "$0")/../.."
exec docker compose -f docker-compose.prod.yml --env-file .env.production "$@"
