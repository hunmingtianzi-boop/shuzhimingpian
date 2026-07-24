#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/cf-ai-card/current}"
ENV_FILE="${ENV_FILE:-/opt/cf-ai-card/.env.production}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/shuzimingpian}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-cf-ai-card-prod}"
MIN_FREE_KB="${MIN_FREE_KB:-1048576}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FINAL_DIR="${BACKUP_ROOT}/daily/${STAMP}"
PARTIAL_DIR="${FINAL_DIR}.partial"
LOG_FILE="${BACKUP_ROOT}/backup.log"
MINIO_CONTAINER_TO_RESUME=""

mkdir -p "${BACKUP_ROOT}"/{daily,weekly,monthly}
touch "${LOG_FILE}"
chmod 700 "${BACKUP_ROOT}" "${BACKUP_ROOT}"/{daily,weekly,monthly}
chmod 600 "${LOG_FILE}"

exec 9>"${BACKUP_ROOT}/.backup.lock"
flock -n 9 || { echo "another backup is already running" >&2; exit 75; }

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "${LOG_FILE}"; }
resume_minio() {
  if [[ -n "${MINIO_CONTAINER_TO_RESUME}" ]]; then
    docker unpause "${MINIO_CONTAINER_TO_RESUME}" >/dev/null 2>&1 || true
    MINIO_CONTAINER_TO_RESUME=""
  fi
}
fail() {
  resume_minio
  log "FAILED: $*"
  rm -rf -- "${PARTIAL_DIR}"
  exit 1
}
trap 'fail "unexpected error at line ${LINENO}"' ERR
trap resume_minio EXIT

[[ -f "${ENV_FILE}" ]] || fail "environment file is missing"
[[ -f "${APP_ROOT}/infra/compose.yaml" ]] || fail "application release is missing"

available_kb="$(df -Pk "${BACKUP_ROOT}" | awk 'NR==2 {print $4}')"
(( available_kb >= MIN_FREE_KB )) || fail "less than ${MIN_FREE_KB} KiB free"

rm -rf -- "${PARTIAL_DIR}"
mkdir -p "${PARTIAL_DIR}"
chmod 700 "${PARTIAL_DIR}"

compose=(docker compose --project-name "${COMPOSE_PROJECT}" --env-file "${ENV_FILE}" -f "${APP_ROOT}/infra/compose.yaml" -f "${APP_ROOT}/infra/compose.production.yaml")

log "starting PostgreSQL dump"
"${compose[@]}" exec -T postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=9' \
  >"${PARTIAL_DIR}/postgres.dump"
[[ -s "${PARTIAL_DIR}/postgres.dump" ]] || fail "PostgreSQL dump is empty"

log "starting object-storage dump"
minio_container="$("${compose[@]}" ps -q minio)"
redis_container="$("${compose[@]}" ps -q redis)"
[[ -n "${minio_container}" && -n "${redis_container}" ]] || fail "backup containers are unavailable"
minio_volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${minio_container}")"
helper_image="$(docker inspect --format '{{.Config.Image}}' "${redis_container}")"
[[ -n "${minio_volume}" && -n "${helper_image}" ]] || fail "object-storage volume metadata is unavailable"
log "pausing object storage for a filesystem-consistent snapshot"
docker pause "${minio_container}" >/dev/null
MINIO_CONTAINER_TO_RESUME="${minio_container}"
docker run --rm --network none \
  --volume "${minio_volume}:/data:ro" \
  "${helper_image}" tar -C /data -czf - . \
  >"${PARTIAL_DIR}/object-storage.tar.gz"
docker unpause "${minio_container}" >/dev/null
MINIO_CONTAINER_TO_RESUME=""
[[ -s "${PARTIAL_DIR}/object-storage.tar.gz" ]] || fail "object-storage dump is empty"

log "archiving deployment configuration"
deployment_config_paths=(
  "${ENV_FILE#/}"
  "${APP_ROOT#/}/infra/compose.yaml"
  "${APP_ROOT#/}/infra/compose.production.yaml"
)
for optional_path in \
  "${APP_ROOT#/}/infra/compose.public-ip.yaml" \
  "${APP_ROOT#/}/infra/compose.public-reuse.yaml" \
  "${APP_ROOT#/}/infra/compose.release.yaml" \
  "${APP_ROOT#/}/infra/host-nginx"; do
  if [[ -e "/${optional_path}" ]]; then
    deployment_config_paths+=("${optional_path}")
  fi
done
tar -C / -czf "${PARTIAL_DIR}/deployment-config.tar.gz" "${deployment_config_paths[@]}"

docker ps \
  --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" \
  --format '{{.Label "com.docker.compose.service"}}	{{.Image}}	{{.ID}}' |
  sort >"${PARTIAL_DIR}/running-containers.txt"
[[ -s "${PARTIAL_DIR}/running-containers.txt" ]] || fail "running container manifest is empty"

checksum_files=(
  postgres.dump
  object-storage.tar.gz
  deployment-config.tar.gz
  running-containers.txt
)
if [[ -f "${APP_ROOT}/DEPLOYED_COMMIT" ]]; then
  cp -- "${APP_ROOT}/DEPLOYED_COMMIT" "${PARTIAL_DIR}/DEPLOYED_COMMIT"
  checksum_files+=(DEPLOYED_COMMIT)
fi

(cd "${PARTIAL_DIR}" && sha256sum "${checksum_files[@]}" >SHA256SUMS)
cat >"${PARTIAL_DIR}/manifest.json" <<EOF
{"created_at":"$(date -u +%FT%TZ)","host":"$(hostname -f)","project":"${COMPOSE_PROJECT}","status":"complete"}
EOF

mv -- "${PARTIAL_DIR}" "${FINAL_DIR}"

day_of_week="$(date -u +%u)"
day_of_month="$(date -u +%d)"
if [[ "${day_of_week}" == "7" ]]; then cp -al -- "${FINAL_DIR}" "${BACKUP_ROOT}/weekly/${STAMP}"; fi
if [[ "${day_of_month}" == "01" ]]; then cp -al -- "${FINAL_DIR}" "${BACKUP_ROOT}/monthly/${STAMP}"; fi

find "${BACKUP_ROOT}/daily" -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf -- {} +
find "${BACKUP_ROOT}/weekly" -mindepth 1 -maxdepth 1 -type d -mtime +28 -exec rm -rf -- {} +
find "${BACKUP_ROOT}/monthly" -mindepth 1 -maxdepth 1 -type d -mtime +186 -exec rm -rf -- {} +

trap - ERR EXIT
log "backup completed: ${FINAL_DIR}"
