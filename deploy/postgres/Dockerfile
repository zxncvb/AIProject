FROM postgres:16-alpine

# The image is used only by docker-compose.pitr.yml. Production Kubernetes
# deployments should use the PostgreSQL operator's managed WAL archiver.
RUN apk add --no-cache aws-cli
COPY deploy/backup/wal-archive.sh /usr/local/bin/wal-archive.sh
COPY deploy/backup/pitr-check.sh /usr/local/bin/pitr-check.sh
RUN chmod 0755 /usr/local/bin/wal-archive.sh
RUN chmod 0755 /usr/local/bin/pitr-check.sh
