#!/bin/bash
set -euo pipefail
umask 077
exec 9>/run/lock/hetzner-gcs-backup.lock
flock -w 600 9
install -d -m 0700 /var/backups/qwntik-postiz
stage=$(mktemp -d /var/backups/qwntik-postiz/.stage.XXXXXXXX)
trap 'rm -rf "$stage"' EXIT
docker exec postiz-central-db-1 pg_dump -U postgres -p 57322 -d postgres -Fc > "$stage/postiz.dump"
docker exec postiz-temporal-db-1 pg_dump -U postgres -p 58322 -d postgres -Fc > "$stage/temporal.dump"
docker exec -i postiz-central-db-1 pg_restore -l < "$stage/postiz.dump" > "$stage/postiz-dump-index.txt"
docker exec qwntik-postiz-postiz-redis redis-cli SAVE > /dev/null
docker cp qwntik-postiz-postiz-redis:/data/dump.rdb "$stage/redis.rdb"
for volume in postiz-config postiz-uploads; do
  source_path=$(docker volume inspect "qwntik-postiz_${volume}" --format '{{.Mountpoint}}')
  tar -C "$source_path" -czf "$stage/${volume}.tar.gz" .
done
tar -C /opt/qwntik-postiz -czf "$stage/deployment.tar.gz" compose.yaml dynamicconfig image-receipt.json bootstrap-credentials.json api-key.txt RUNBOOK.md traefik-route.staged.yaml verification-receipt.json public-verification-receipt.json mausbot-connection-receipt.json postiz-mail.env secrets/resend-key.txt postiz-het34-source.tar.gz HET-34-migration.sql HET-34-release-receipt.json compose.rollback-private.yaml HET-34-hosted-checks.json HET-34-full-smoke-receipt.json het34-a7ba-tests.log HET-34-runtime-a7ba.sha256 compose.before-het34.yaml HET-34-production-migration.log HET-34-production-verification.json HET-34-production-schema-parity.log HET-34-human-email-receipt.json HET-34-fixture-mail-metadata.json het34-smoke.yaml het34-smoke-flow.py
tar --exclude="*/volumes/db/data" --exclude="*/volumes/storage" --exclude="*/.git" -C /opt/quantic-impact/clients -czf "$stage/managed-projects.tar.gz" postiz-central/supabase/docker postiz-temporal/supabase/docker
tar -C /opt/qwntik-postiz -czf "$stage/het35-recovery.tar.gz" het35
(cd "$stage" && sha256sum ./* > SHA256SUMS)
rm -rf /var/backups/qwntik-postiz/previous
if [ -d /var/backups/qwntik-postiz/current ]; then mv /var/backups/qwntik-postiz/current /var/backups/qwntik-postiz/previous; fi
mv "$stage" /var/backups/qwntik-postiz/current
trap - EXIT
set -a
source /etc/restic/hetzner-gcs.env
set +a
export RESTIC_PASSWORD_FILE=/etc/restic/coolify-recovery.pass
export GOMAXPROCS=2
export GOMEMLIMIT=1536MiB
input_bytes=$(du -sb /var/backups/qwntik-postiz/current | cut -f1)
bucket_bytes=$(/usr/local/sbin/hetzner-gcs-size)
if (( input_bytes > 8*1024*1024*1024 || bucket_bytes+input_bytes+1024*1024*1024 > 100*1024*1024*1024 )); then
 echo 'Postiz backup size guard refused upload' >&2
 exit 1
fi
restic backup /var/backups/qwntik-postiz/current --tag qwntik-postiz --host quantic-impact-ash-01
restic forget --tag qwntik-postiz --keep-daily 7 --keep-weekly 4 --keep-monthly 2
restic check
