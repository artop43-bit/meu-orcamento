#!/bin/sh
# Agenda o backup diário (padrão: 03:30, horário de Brasília) com o crond do Alpine.
set -eu

: "${BACKUP_AGE_RECIPIENT:?Defina BACKUP_AGE_RECIPIENT (chave pública age) no .env.production}"

SCHEDULE="${BACKUP_SCHEDULE:-30 3 * * *}"
export TZ="${TZ:-America/Sao_Paulo}"

# O crond não herda o ambiente: grava as variáveis necessárias para o script.
# "export -p" já sai com aspas corretas (senhas podem ter caracteres especiais).
umask 077
export -p | grep -E "^export (PG|BACKUP_|OCI_|TZ=)" > /etc/backup.env

echo "$SCHEDULE . /etc/backup.env && /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1" > /etc/crontabs/root

echo "Backup agendado: '$SCHEDULE' ($TZ)."
if [ "${BACKUP_ON_START:-false}" = "true" ]; then
  /usr/local/bin/backup.sh
fi

exec crond -f -l 8
