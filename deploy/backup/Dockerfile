FROM postgres:16-alpine
RUN apk add --no-cache bash coreutils tar gzip age aws-cli
COPY backup.sh restore.sh dr-test.sh /usr/local/bin/
RUN chmod 0555 /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/dr-test.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
