#!/usr/bin/env bash
# Migra o Meu Orçamento de uma VM para outra (ex.: A2 → A1.Flex Always Free), sem perder dados.
# Roda no SEU PC (Git Bash/Linux/macOS), com a mesma chave SSH nas duas VMs.
#
#   deploy/scripts/migrate-host.sh <fase> <IP_ANTIGO> <IP_NOVO> [chave_ssh]
#
# Fases (nesta ordem; cada uma pode ser repetida com segurança):
#   preparar   instala o servidor novo, copia chaves e .env.production (sem imprimir segredos),
#              clona o repositório, copia o certificado e constrói as imagens. O site segue no ar.
#   trocar     janela de manutenção (alguns minutos): para o app na VM antiga, copia o banco
#              (pg_dump → pg_restore) e os backups, sobe tudo na nova e confere os dados.
#   ensaiar    (opcional, a qualquer hora) testa a cópia do banco sem parar o site.
#   voltar     desfaz a troca: religa o app na VM antiga (use antes de mover o IP).
#   concluir   depois de mover o IP reservado no console: confere o site pelo endereço público.
#
# Ver docs/MIGRACAO-A1.md. Nenhum segredo passa pela tela: tudo vai de uma VM para a outra
# por um "cano" SSH através do PC.
set -euo pipefail

PHASE="${1:-}"
OLD="${2:-}"
NEW="${3:-}"
KEY="${4:-$HOME/.ssh/oracle-meu-orcamento.key}"
APP_DIR="meu-orcamento"
REPO="git@github.com:artop43-bit/meu-orcamento.git"
TABLES="users expenses incomes categories recurring_items goals investments money_accounts support_threads announcements stored_files"

if [ -z "$PHASE" ] || [ -z "$OLD" ] || { [ -z "$NEW" ] && [ "$PHASE" != "ensaiar" ]; }; then
  sed -n '2,20p' "$0"
  exit 1
fi

SSH_OPTS=(-i "$KEY" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=6)
old() { ssh "${SSH_OPTS[@]}" "ubuntu@$OLD" "$@"; }
new() { ssh "${SSH_OPTS[@]}" -o StrictHostKeyChecking=accept-new "ubuntu@$NEW" "$@"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
compose_old() { old "cd ~/$APP_DIR && deploy/scripts/compose.sh $*"; }
compose_new() { new "cd ~/$APP_DIR && deploy/scripts/compose.sh $*"; }
domain() { old "grep -E '^DOMAIN=' ~/$APP_DIR/.env.production | cut -d= -f2-"; }

counts() {
  # Contagem de linhas das tabelas principais (para comparar antiga x nova). O SQL vai pela
  # entrada padrão, sem brigar com as aspas do ssh e do docker.
  local where="$1" sql=""
  for t in $TABLES; do sql="$sql SELECT '$t', count(*) FROM $t UNION ALL"; done
  sql="${sql% UNION ALL};"
  echo "$sql" | "$where" "cd ~/$APP_DIR && deploy/scripts/compose.sh exec -T db sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tA -F='"
}

case "$PHASE" in
preparar)
  step "Conferindo o acesso às duas VMs"
  old "echo antiga ok: \$(hostname)"
  new "echo nova ok: \$(hostname) \$(uname -m)"

  step "Instalando o servidor novo (Docker, firewall, SSH endurecido, fail2ban)"
  scp "${SSH_OPTS[@]}" -o StrictHostKeyChecking=accept-new deploy/scripts/setup-server.sh "ubuntu@$NEW:/tmp/setup-server.sh"
  new "command -v docker >/dev/null && echo 'Docker já instalado' || bash /tmp/setup-server.sh"

  step "Copiando a chave de leitura do GitHub (VM → VM, sem passar pela tela)"
  old "cat ~/.ssh/github_deploy" | new "umask 077; mkdir -p ~/.ssh; cat > ~/.ssh/github_deploy"
  old "cat ~/.ssh/github_deploy.pub" | new "cat > ~/.ssh/github_deploy.pub"
  new "grep -q 'Host github.com' ~/.ssh/config 2>/dev/null || printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config; chmod 600 ~/.ssh/config"
  new "ssh-keyscan -t ed25519 github.com 2>/dev/null >> ~/.ssh/known_hosts"

  step "Clonando o repositório"
  new "[ -d ~/$APP_DIR/.git ] && (cd ~/$APP_DIR && git fetch -q origin main && git reset -q --hard origin/main) || git clone -q $REPO ~/$APP_DIR"
  new "cd ~/$APP_DIR && git log --oneline -1"

  step "Copiando o .env.production (VM → VM, permissão 600)"
  old "cat ~/$APP_DIR/.env.production" | new "umask 077; cat > ~/$APP_DIR/.env.production"
  new "test -s ~/$APP_DIR/.env.production && echo '.env.production copiado' && stat -c '%a' ~/$APP_DIR/.env.production"

  step "Copiando o certificado HTTPS do Caddy (evita emitir de novo)"
  new "docker volume create meu-orcamento_caddy_data >/dev/null"
  old "docker run --rm -v meu-orcamento_caddy_data:/v alpine tar czf - -C /v ." \
    | new "docker run --rm -i -v meu-orcamento_caddy_data:/v alpine tar xzf - -C /v"

  step "Construindo as imagens na VM nova (o site continua na antiga)"
  compose_new "build -q"
  compose_new "pull -q db" || true
  echo
  echo "Preparação concluída. Próximo passo: $0 trocar $OLD $NEW"
  ;;

trocar)
  step "Contagem de dados na VM antiga (antes de parar)"
  BEFORE="$(counts old)"
  echo "$BEFORE"

  step "Janela de manutenção: parando o app na VM antiga (o banco continua ligado)"
  compose_old "stop caddy api scheduler backup"

  step "Subindo só o banco na VM nova"
  compose_new "up -d db"
  for _ in $(seq 1 60); do
    if compose_new "exec -T db sh -c 'pg_isready -q -U \"\$POSTGRES_USER\"'" 2>/dev/null; then break; fi
    sleep 2
  done

  step "Copiando o banco (pg_dump → pg_restore, VM → VM)"
  compose_old "exec -T db sh -c 'pg_dump -Fc -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\"'" \
    | compose_new "exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'"     || echo "(o pg_restore terminou com avisos; a conferência das contagens abaixo decide)"

  step "Copiando os backups diários já feitos"
  new "docker volume create meu-orcamento_backups >/dev/null"
  old "docker run --rm -v meu-orcamento_backups:/v alpine tar czf - -C /v ." \
    | new "docker run --rm -i -v meu-orcamento_backups:/v alpine tar xzf - -C /v"

  step "Conferindo os dados na VM nova"
  AFTER="$(counts new)"
  echo "$AFTER"
  if [ "$BEFORE" != "$AFTER" ]; then
    echo "As contagens não batem. Nada foi trocado de verdade: rode '$0 voltar $OLD $NEW'." >&2
    exit 1
  fi

  step "Subindo tudo na VM nova"
  compose_new "up -d --wait --wait-timeout 300"
  compose_new "ps"

  step "Testando o site na VM nova (antes de mover o IP)"
  HOST="$(domain)"
  curl -fsS --max-time 20 --resolve "$HOST:443:$NEW" "https://$HOST/api/health/db" && echo
  echo
  echo "Tudo certo na VM nova. Agora, no console da Oracle, mova o IP reservado para a VM nova"
  echo "(docs/MIGRACAO-A1.md, passo 4) e depois rode: $0 concluir $OLD $NEW"
  echo "Se algo der errado ANTES de mover o IP: $0 voltar $OLD $NEW"
  ;;

ensaiar)
  # Ensaio sem parar o site: copia o banco pelo mesmo caminho da troca para um PostgreSQL
  # descartável na própria VM antiga e compara as contagens. Uso: ensaiar <IP_ANTIGO> -
  step "Contagem de dados na VM (produção)"
  BEFORE="$(counts old)"
  echo "$BEFORE"
  step "PostgreSQL descartável"
  old "docker rm -f mo-ensaio >/dev/null 2>&1; docker run -d --name mo-ensaio -e POSTGRES_USER=ensaio -e POSTGRES_PASSWORD=ensaio -e POSTGRES_DB=ensaio postgres:17-alpine >/dev/null"
  for _ in $(seq 1 60); do old "docker exec mo-ensaio pg_isready -q -U ensaio" 2>/dev/null && break; sleep 2; done
  sleep 2
  step "pg_dump (produção) → pg_restore (descartável), pelo PC"
  compose_old "exec -T db sh -c 'pg_dump -Fc -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\"'"     | old "docker exec -i mo-ensaio pg_restore --no-owner -U ensaio -d ensaio"     || echo "(o pg_restore terminou com avisos; a conferência decide)"
  step "Contagem no banco restaurado"
  sql=""
  for t in $TABLES; do sql="$sql SELECT '$t', count(*) FROM $t UNION ALL"; done
  AFTER="$(echo "${sql% UNION ALL};" | old "docker exec -i mo-ensaio psql -U ensaio -d ensaio -tA -F=")"
  echo "$AFTER"
  old "docker rm -f mo-ensaio >/dev/null"
  step "Tamanho dos volumes que serão copiados"
  old "docker run --rm -v meu-orcamento_backups:/b -v meu-orcamento_caddy_data:/c alpine du -sh /b /c"
  if [ "$BEFORE" = "$AFTER" ]; then echo; echo "Ensaio OK: os dados copiados batem com a produção."; else echo "As contagens não batem." >&2; exit 1; fi
  ;;

voltar)
  step "Religando o app na VM antiga"
  compose_old "start caddy api scheduler backup"
  compose_old "ps"
  new "cd ~/$APP_DIR && deploy/scripts/compose.sh stop" || true
  echo "O site voltou para a VM antiga."
  ;;

concluir)
  # Aqui $OLD é o IP público antigo, que agora aponta para a VM nova.
  HOST="$(new "grep -E '^DOMAIN=' ~/$APP_DIR/.env.production | cut -d= -f2-")"
  step "Conferindo o site pelo endereço público ($HOST)"
  ssh-keygen -R "$OLD" >/dev/null 2>&1 || true
  curl -fsS --max-time 20 "https://$HOST/api/health/db" && echo
  ssh "${SSH_OPTS[@]}" -o StrictHostKeyChecking=accept-new "ubuntu@$OLD" "hostname; uname -m; cd ~/$APP_DIR && deploy/scripts/compose.sh ps --format '{{.Service}} {{.Status}}'"
  echo
  echo "Migração concluída. Mantenha a VM antiga DESLIGADA (não apague) por uns dias como garantia;"
  echo "depois, termine a instância antiga no console (com o volume de boot)."
  ;;

*)
  echo "Fase desconhecida: $PHASE (use preparar, trocar, voltar ou concluir)." >&2
  exit 1
  ;;
esac
