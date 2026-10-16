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

site_ok() { curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:5173/ 2> /dev/null; }
api_ok() { curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:8000/api/health 2> /dev/null; }

show_info() {
  cat <<INFO

=====================================================================
 Meu Orçamento está no ar!

 Abra a aba "PORTS" (Portas) e clique no globo da porta 5173,
 ou acesse: $FRONTEND_URL

 Conta de demonstração (senha nova a cada vez que o Codespace liga):
$(sed "s/^/   /" "$ROOT/.devcontainer/credenciais.txt" 2> /dev/null)

 Para ver de novo:  cat .devcontainer/credenciais.txt
=====================================================================
INFO
}

# --se-parado (usado ao abrir o editor): não mexe em nada se o app já estiver rodando.
if [ "${1:-}" = "--se-parado" ] && site_ok && api_ok; then
  show_info
  exit 0
fi

# Para processos de uma execução anterior (ao religar o Codespace).
pkill -f "uvicorn app.main:app" 2> /dev/null || true
pkill -f "vite" 2> /dev/null || true

# Dependências mudaram (ex.: trocou de branch)? Reinstala antes de subir.
DEPS_HASH="$(cat "$ROOT/backend/uv.lock" "$ROOT/frontend/package-lock.json" | sha256sum | cut -d' ' -f1)"
if [ "$(cat "$ROOT/.devcontainer/.deps-hash" 2> /dev/null)" != "$DEPS_HASH" ] \
  || [ ! -d "$ROOT/frontend/node_modules" ] || [ ! -d "$ROOT/backend/.venv" ]; then
  echo "Dependências novas: instalando (1–2 minutos)…"
  bash "$ROOT/.devcontainer/setup.sh"
  echo "$DEPS_HASH" > "$ROOT/.devcontainer/.deps-hash"
fi

cd "$ROOT/backend"
uv run alembic upgrade head > /tmp/migrations.log 2>&1
# v0.4.3: a conta de demonstração vem preenchida (6 meses de exemplo). Na primeira vez com
# esta versão ela é refeita; depois disso, o que você lançar fica guardado.
RESET=""
if [ ! -f "$ROOT/.devcontainer/.demo-v043" ]; then
  RESET="--reset"
fi
uv run python -m app.cli seed-demo $RESET --credentials-file "$ROOT/.devcontainer/credenciais.txt" > /tmp/seed.log 2>&1
touch "$ROOT/.devcontainer/.demo-v043"
chmod 600 "$ROOT/.devcontainer/credenciais.txt"

# setsid -f: os processos ficam numa sessão própria e continuam rodando depois que este
# script (e o comando de inicialização do Codespace) termina.
setsid -f nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload \
  > /tmp/api.log 2>&1 < /dev/null

cd "$ROOT/frontend"
API_PROXY_TARGET="http://127.0.0.1:8000" setsid -f nohup npm run dev -- --clearScreen false > /tmp/web.log 2>&1 < /dev/null

# Espera o site responder (até 60 s) para não mostrar o link antes da hora.
for _ in $(seq 1 60); do
  site_ok && api_ok && break
  sleep 1
done
if ! site_ok || ! api_ok; then
  echo "O app não subiu. Veja o erro com: tail -n 30 /tmp/web.log /tmp/api.log" >&2
  exit 1
fi

show_info
