#!/usr/bin/env bash
# Teste completo da stack de produção em https://localhost (usado pelo CI; roda também
# localmente com Docker, em Linux/WSL/Git Bash). Precisa de: docker, curl, age.
#
# Sobe tudo com docker-compose.prod.yml e confere: site, API, cabeçalhos de segurança,
# cadastro/login com cookie seguro, banco inacessível de fora, limpeza agendada e um
# backup gerado, descriptografado e restaurado num banco novo.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ -f .env.production ]; then
  echo "Já existe um .env.production aqui; rode o teste numa cópia limpa do repositório." >&2
  exit 1
fi

WORK="$(mktemp -d)"
COMPOSE=(docker compose -p meu-orcamento-smoke -f docker-compose.prod.yml --env-file .env.production)
BASE="https://localhost"
JAR="$WORK/cookies.txt"
EMAIL="smoke@example.com"
PASSWORD="senha-de-teste-123"

pass() { printf '  \033[32mok\033[0m  %s\n' "$*"; }
fail() { printf '  \033[31mFALHOU\033[0m  %s\n' "$*"; exit 1; }
# check "descrição" comando...  -> ok se o comando der certo, senão encerra com erro.
check() {
  local description="$1"
  shift
  if "$@" > /dev/null 2>&1; then pass "$description"; else fail "$description"; fi
}
get() { curl -sSk --max-time 20 "$@"; }
api() { get -b "$JAR" -c "$JAR" -H "Content-Type: application/json" -H "X-Requested-With: fetch" "$@"; }

cleanup() {
  local status=$?
  if [ "$status" -ne 0 ]; then
    echo "--- logs (últimas linhas) ---"
    "${COMPOSE[@]}" logs --tail 80 || true
  fi
  "${COMPOSE[@]}" down -v --remove-orphans > /dev/null 2>&1 || true
  rm -f .env.production
  rm -rf "$WORK"
  exit "$status"
}
trap cleanup EXIT

echo "==> Preparando ambiente de teste"
age-keygen -o "$WORK/age-key.txt" 2> /dev/null
RECIPIENT="$(grep -o 'age1[0-9a-z]*' "$WORK/age-key.txt" | head -1)"
umask 077
cat > .env.production <<EOF
DOMAIN=localhost
POSTGRES_USER=orcamento
POSTGRES_DB=orcamento
POSTGRES_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
SECRET_KEY=$(head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n')
EMAIL_BACKEND=console
EMAIL_FROM=Meu Orçamento <nao-responda@localhost>
BACKUP_AGE_RECIPIENT=$RECIPIENT
EOF
umask 022

echo "==> Construindo e subindo (pode levar alguns minutos)"
"${COMPOSE[@]}" up -d --build --wait --wait-timeout 300

echo "==> Site e API"
check "frontend servido em HTTPS" grep -q "<title>Meu Orçamento</title>" <(get "$BASE/")
check "rotas do app caem no index.html" grep -q 'id="root"' <(get "$BASE/orcamento/2030-01")
check "API conectada ao PostgreSQL" grep -q '"database":"ok"' <(get "$BASE/api/health/db")
code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost/")"
check "HTTP redireciona para HTTPS ($code)" test "$code" = 308 -o "$code" = 301

echo "==> Cabeçalhos de segurança"
get -D "$WORK/h-site" -o /dev/null "$BASE/"
get -D "$WORK/h-api" -o /dev/null "$BASE/api/health"
for header in "strict-transport-security:" "content-security-policy:" "x-frame-options: DENY" "x-content-type-options: nosniff"; do
  check "$header" grep -qi "^$header" "$WORK/h-site"
done
check "cabeçalho Server oculto" bash -c "! grep -qi '^server:' '$WORK/h-site'"
check "API com Cache-Control: no-store" grep -qi "^cache-control: no-store" "$WORK/h-api"

echo "==> Banco inacessível de fora"
check "porta 5432 fechada no host" bash -c "! (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null"

echo "==> Cadastro, confirmação e login"
api -X POST "$BASE/api/auth/register" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"accept_terms\":true}" > /dev/null
sleep 2
"${COMPOSE[@]}" logs api > "$WORK/api.log" 2>&1
token="$(grep -o 'verificar-email?token=[A-Za-z0-9_-]*' "$WORK/api.log" | tail -1 | cut -d= -f2)"
check "e-mail de confirmação gerado" test -n "$token"
check "link do e-mail usa https://localhost" grep -q "https://localhost/verificar-email" "$WORK/api.log"
check "e-mail confirmado" grep -q "confirmado" <(api -X POST "$BASE/api/auth/verify-email" -d "{\"token\":\"$token\"}")
check "login" grep -q '"status":"ok"' <(api -X POST "$BASE/api/auth/login" -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
check "cookie __Host-session (Secure)" grep -q "__Host-session" "$JAR"
api -X POST "$BASE/api/months/2030-01/expenses" -d '{"description":"Aluguel","amount":"1500.00"}' > /dev/null
check "lançamento gravado e lido" grep -q '"expense_total":"1500.00"' <(api "$BASE/api/months/2030-01")
csrf="$(curl -sk -o /dev/null -w '%{http_code}' -b "$JAR" -X POST -H "Content-Type: application/json" "$BASE/api/auth/logout")"
check "proteção CSRF ativa ($csrf)" test "$csrf" = 403
check "evento de segurança com IP" grep -q '"ip":"[0-9a-f.:]\+"' <(api "$BASE/api/auth/events")

echo "==> Tarefas agendadas"
check "limpeza rodou ao iniciar" grep -q "Removidos:" <("${COMPOSE[@]}" logs scheduler 2>&1)

echo "==> Backup e restauração"
"${COMPOSE[@]}" exec -T backup sh -c '. /etc/backup.env && backup.sh' > "$WORK/backup.log" 2>&1 \
  || { cat "$WORK/backup.log"; fail "backup.sh terminou com erro"; }
file="$(grep -o 'meu-orcamento_[0-9_-]*\.dump\.age' "$WORK/backup.log" | head -1)"
check "backup gerado: ${file:-nenhum}" test -n "$file"
"${COMPOSE[@]}" exec -T backup cat "/backups/$file" > "$WORK/backup.age"
check "arquivo criptografado (age)" grep -q "age-encryption.org" <(head -c 40 "$WORK/backup.age")
check "descriptografado com a chave privada" age -d -i "$WORK/age-key.txt" -o "$WORK/backup.dump" "$WORK/backup.age"
"${COMPOSE[@]}" exec -T db sh -c 'createdb -U "$POSTGRES_USER" restauracao'
"${COMPOSE[@]}" exec -T db sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d restauracao' < "$WORK/backup.dump"
count() {
  "${COMPOSE[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d restauracao -tAc 'SELECT count(*) FROM $1'"
}
check "restaurado num banco novo: usuários = $(count users)" test "$(count users)" = 1
check "restaurado num banco novo: contas = $(count expenses)" test "$(count expenses)" = 1

echo
echo "Todos os testes de produção passaram."
