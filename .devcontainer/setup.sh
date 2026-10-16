#!/usr/bin/env bash
# Roda uma vez, quando o Codespace é criado: instala as dependências.
set -euo pipefail
cd "$(dirname "$0")/.."

pip install --quiet --user uv
export PATH="$HOME/.local/bin:$PATH"

(cd backend && uv sync)
(cd frontend && npm ci --no-audit --no-fund)

echo "Dependências instaladas."
