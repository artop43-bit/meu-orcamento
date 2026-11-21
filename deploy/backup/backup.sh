#!/bin/sh
# Faz o dump do banco, criptografa e envia ao Object Storage da Oracle (compatível com S3).
#
# Só a chave PÚBLICA age fica no servidor: ele consegue criptografar, mas não abrir os
# backups. A chave privada fica com o dono (veja docs/DEPLOY.md, "Restaurar um backup").
set -eu
# Se o pg_dump falhar no meio do pipe, o backup inteiro falha (sem arquivo pela metade).
set -o pipefail

STAMP="$(date +%Y-%m-%d_%H%M)"
FILE="/backups/meu-orcamento_${STAMP}.dump.age"
LOCAL_DAYS="${BACKUP_LOCAL_RETENTION_DAYS:-7}"
# Remoto: 7 cópias diárias + 4 semanais (~11 no total), para caber no Object Storage gratuito.
REMOTE_DAILY_DAYS="${BACKUP_REMOTE_DAILY_DAYS:-7}"
REMOTE_WEEKLY_DAYS="${BACKUP_REMOTE_WEEKLY_DAYS:-29}"
# Backups antigos (antes das pastas diario/ e semanal/) saem no prazo que valia para eles.
LEGACY_DAYS="${BACKUP_REMOTE_RETENTION_DAYS:-30}"

echo "[backup] $(date -Iseconds) iniciando"

# -Fc: formato customizado (comprimido, restaurável com pg_restore).
# As mídias da Mensageria são temporárias (somem em 7 dias): entra só a estrutura da tabela,
# sem os arquivos. Restaurar exige soltar as referências a elas (ver docs/DEPLOY.md).
pg_dump -Fc --no-owner --no-privileges --exclude-table-data=messaging_media | age -r "$BACKUP_AGE_RECIPIENT" > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
echo "[backup] gerado $(basename "$FILE") ($(du -h "$FILE" | cut -f1))"

# Cópias locais: só as dos últimos dias (o servidor não é lugar de guardar histórico).
find /backups -name 'meu-orcamento_*.dump.age' -mtime +"$LOCAL_DAYS" -delete

if [ -n "${OCI_S3_ENDPOINT:-}" ] && [ -n "${OCI_BUCKET:-}" ]; then
  export RCLONE_CONFIG_OCI_TYPE=s3
  export RCLONE_CONFIG_OCI_PROVIDER=Other
  export RCLONE_CONFIG_OCI_ENDPOINT="$OCI_S3_ENDPOINT"
  export RCLONE_CONFIG_OCI_REGION="${OCI_REGION:-sa-saopaulo-1}"
  export RCLONE_CONFIG_OCI_ACCESS_KEY_ID="$OCI_ACCESS_KEY_ID"
  export RCLONE_CONFIG_OCI_SECRET_ACCESS_KEY="$OCI_SECRET_ACCESS_KEY"
  export RCLONE_CONFIG_OCI_FORCE_PATH_STYLE=true
  export RCLONE_CONFIG_OCI_NO_CHECK_BUCKET=true

  rclone copy "$FILE" "oci:${OCI_BUCKET}/diario/" --s3-no-check-bucket
  echo "[backup] enviado para ${OCI_BUCKET}/diario"
  # Domingo: também guarda a cópia semanal.
  if [ "$(date +%u)" = "7" ]; then
    rclone copy "$FILE" "oci:${OCI_BUCKET}/semanal/" --s3-no-check-bucket
    echo "[backup] cópia semanal em ${OCI_BUCKET}/semanal"
  fi
  # Retenção remota descrita na Política de privacidade.
  rclone delete "oci:${OCI_BUCKET}/diario/" --min-age "${REMOTE_DAILY_DAYS}d" --include 'meu-orcamento_*.dump.age'
  rclone delete "oci:${OCI_BUCKET}/semanal/" --min-age "${REMOTE_WEEKLY_DAYS}d" --include 'meu-orcamento_*.dump.age'
  rclone delete "oci:${OCI_BUCKET}/" --max-depth 1 --min-age "${LEGACY_DAYS}d" --include 'meu-orcamento_*.dump.age'
else
  echo "[backup] AVISO: OCI_S3_ENDPOINT/OCI_BUCKET não definidos; backup ficou só no servidor."
fi

echo "[backup] $(date -Iseconds) concluído"
