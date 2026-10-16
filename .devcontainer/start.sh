#!/usr/bin/env bash
# Roda toda vez que o Codespace liga: prepara o banco, cria a conta de demonstração
# e sobe a API (porta 8000) e o site (porta 5173) em segundo plano.
#
# Banco: SQLite num arquivo local (backend/codespace.db), suficiente para testar.
# Logs: /tmp/api.log e /tmp/web.log. E-mails aparecem no /tmp/api.log.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
export PATH="$HOME/.local/bin:$PATH"

export ENVIRONMENT=development
export DATABASE_URL="sqlite+pysqlite:///$ROOT/backend/codespace.db"
export EMAIL_BACKEND=console
export SECRET_KEY="codespace-$(hostname)"
if [ -n "${CODESPACE_NAME:-}" ]; then
  FRONTEND_URL="https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
else
  FRONTEND_URL="http://localhost:5173"
fi
export FRONTEND_URL

# Para processos de uma execução anterior (ao religar o Codespace).
pkill -f "uvicorn app.main:app" 2> /dev/null || true
pkill -f "vite" 2> /dev/null || true

cd "$ROOT/backend"
uv run alembic upgrade head > /tmp/migrations.log 2>&1
uv run python -m app.cli seed-demo --credentials-file "$ROOT/.devcontainer/credenciais.txt" > /tmp/seed.log 2>&1
chmod 600 "$ROOT/.devcontainer/credenciais.txt"

# setsid: os processos continuam rodando depois que este script termina.
setsid nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload \
  > /tmp/api.log 2>&1 < /dev/null &

cd "$ROOT/frontend"
API_PROXY_TARGET="http://127.0.0.1:8000" setsid nohup npm run dev > /tmp/web.log 2>&1 < /dev/null &

cat <<EOF

=====================================================================
 Meu Orçamento está subindo (leva uns 10 segundos).

 Abra a aba "PORTS" (Portas) e clique no globo da porta 5173,
 ou acesse: $FRONTEND_URL

 Conta de demonstração (senha nova a cada vez que o Codespace liga):
$(sed 's/^/   /' "$ROOT/.devcontainer/credenciais.txt")

 Para ver de novo:  cat .devcontainer/credenciais.txt
=====================================================================
EOF
