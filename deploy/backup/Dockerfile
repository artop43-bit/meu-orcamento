# Backup do PostgreSQL: pg_dump -> criptografa com age -> envia ao Object Storage (rclone).
FROM postgres:18-alpine

RUN apk add --no-cache age rclone tzdata

COPY backup.sh /usr/local/bin/backup.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
