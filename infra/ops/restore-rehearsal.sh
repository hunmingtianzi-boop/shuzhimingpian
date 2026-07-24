#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/cf-ai-card/current}"
ENV_FILE="${ENV_FILE:-/opt/cf-ai-card/.env.production}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/shuzimingpian}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-cf-ai-card-prod}"
REPORT_DIR="${BACKUP_ROOT}/restore-rehearsals"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DATABASE="restore_rehearsal_${STAMP//[^0-9]/}"
STARTED="$(date +%s)"

mkdir -p "${REPORT_DIR}"
chmod 700 "${REPORT_DIR}"

backup_dir="${1:-$(find "${BACKUP_ROOT}/daily" -mindepth 1 -maxdepth 1 -type d ! -name '*.partial' | sort | tail -n 1)}"
[[ -n "${backup_dir}" && -s "${backup_dir}/postgres.dump" ]] || { echo "no usable backup found" >&2; exit 1; }
(cd "${backup_dir}" && sha256sum --check SHA256SUMS)

compose=(docker compose --project-name "${COMPOSE_PROJECT}" --env-file "${ENV_FILE}" -f "${APP_ROOT}/infra/compose.yaml" -f "${APP_ROOT}/infra/compose.production.yaml")

cleanup() {
  "${compose[@]}" exec -T postgres sh -ceu \
    'PGPASSWORD="$POSTGRES_PASSWORD" dropdb -U "$POSTGRES_USER" --if-exists --force "$1"' sh "${DATABASE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${compose[@]}" exec -T postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" createdb -U "$POSTGRES_USER" "$1"' sh "${DATABASE}"
cat "${backup_dir}/postgres.dump" | "${compose[@]}" exec -T postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl --exit-on-error' sh "${DATABASE}"

schema_version="$("${compose[@]}" exec -T postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$1" -Atc "select version_num from alembic_version limit 1"' sh "${DATABASE}")"
table_count="$("${compose[@]}" exec -T postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$1" -Atc "select count(*) from information_schema.tables where table_schema = '\''public'\'' and table_type = '\''BASE TABLE'\''"' sh "${DATABASE}")"
tenant_count="$("${compose[@]}" exec -T postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$1" -Atc "select count(*) from tenants"' sh "${DATABASE}")"

elapsed="$(( $(date +%s) - STARTED ))"
cat >"${REPORT_DIR}/${STAMP}.json" <<EOF
{"completed_at":"$(date -u +%FT%TZ)","backup":"$(basename "${backup_dir}")","schema_version":"${schema_version}","table_count":${table_count},"tenant_count":${tenant_count},"elapsed_seconds":${elapsed},"passed":true}
EOF
chmod 600 "${REPORT_DIR}/${STAMP}.json"
printf 'restore rehearsal passed: %s\n' "${REPORT_DIR}/${STAMP}.json"
