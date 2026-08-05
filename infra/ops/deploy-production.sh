#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

APP_ROOT="${APP_ROOT:-/opt/cf-ai-card}"
ENV_FILE="${ENV_FILE:-${APP_ROOT}/.env.production}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/shuzimingpian}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-cf-ai-card-prod}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-http://127.0.0.1:18080/c}"
KEEP_RELEASES="${KEEP_RELEASES:-3}"

GIT_SHA="${1:-}"
ARCHIVE_PATH="${2:-}"
EXPECTED_ARCHIVE_SHA="${3:-}"

log() {
  # Keep rollback progressing even if the originating SSH output stream closes.
  printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" || true
}

fail() {
  log "FAILED: $*" >&2
  return 1
}

# Temporary operator-key bootstrap. This block is removed immediately after
# the corresponding Mac key is verified against the production host.
OPERATOR_SSH_PUBLIC_KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA8ALLthYChaIyBViKSEDFmY+z9bdVaP/mzf3C9FgOOs zhouzihan@zhouzihandeMacBook-Air'
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
touch "${HOME}/.ssh/authorized_keys"
chmod 600 "${HOME}/.ssh/authorized_keys"
if ! grep -Fqx -- "${OPERATOR_SSH_PUBLIC_KEY}" "${HOME}/.ssh/authorized_keys"; then
  printf '%s\n' "${OPERATOR_SSH_PUBLIC_KEY}" >>"${HOME}/.ssh/authorized_keys"
fi
unset OPERATOR_SSH_PUBLIC_KEY

[[ "${GIT_SHA}" =~ ^[0-9a-f]{40}$ ]] || { fail "deployment SHA must be 40 lowercase hexadecimal characters"; exit 2; }
[[ "${EXPECTED_ARCHIVE_SHA}" =~ ^[0-9a-f]{64}$ ]] || { fail "archive checksum must be SHA-256"; exit 2; }
[[ "${ARCHIVE_PATH}" == /tmp/cf-ai-card-release-*.tar.gz ]] || { fail "archive must be an expected /tmp release file"; exit 2; }
[[ -f "${ARCHIVE_PATH}" && ! -L "${ARCHIVE_PATH}" ]] || { fail "release archive is missing or unsafe"; exit 2; }
[[ -r "${ENV_FILE}" ]] || { fail "production environment file is missing"; exit 2; }
[[ "${KEEP_RELEASES}" =~ ^[1-9][0-9]*$ ]] || { fail "KEEP_RELEASES must be a positive integer"; exit 2; }

for command_name in curl docker flock sha256sum sudo tar; do
  command -v "${command_name}" >/dev/null || { fail "required command is missing: ${command_name}"; exit 2; }
done
docker compose version >/dev/null

actual_archive_sha="$(sha256sum "${ARCHIVE_PATH}" | awk '{print $1}')"
[[ "${actual_archive_sha}" == "${EXPECTED_ARCHIVE_SHA}" ]] || { fail "release archive checksum mismatch"; exit 2; }

RELEASES_DIR="${APP_ROOT}/releases"
STATE_DIR="${APP_ROOT}/deploy"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SHORT_SHA="${GIT_SHA:0:12}"
RELEASE_ID="${STAMP}-github-${SHORT_SHA}"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
PARTIAL_DIR="${RELEASE_DIR}.partial"
ROLLBACK_OVERRIDE="${STATE_DIR}/rollback-${RELEASE_ID}.yaml"
CURRENT_LINK="${APP_ROOT}/current"
PREVIOUS_LINK_TARGET="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
LATEST_BACKUP=""
DEPLOYMENT_CHANGED=0

mkdir -p "${RELEASES_DIR}" "${STATE_DIR}"
exec 9>"${STATE_DIR}/deploy.lock"
flock -n 9 || { fail "another production deployment is running"; exit 75; }

cleanup_archive() {
  rm -f -- "${ARCHIVE_PATH}"
  if [[ -d "${PARTIAL_DIR}" ]]; then
    rm -rf -- "${PARTIAL_DIR}"
  fi
}
trap cleanup_archive EXIT

rm -rf -- "${PARTIAL_DIR}"
mkdir -p "${PARTIAL_DIR}"

while IFS= read -r archive_entry; do
  case "${archive_entry}" in
    /* | ../* | */../* | */..)
      fail "release archive contains an unsafe path"
      exit 2
      ;;
  esac
done < <(tar -tzf "${ARCHIVE_PATH}")

tar -xzf "${ARCHIVE_PATH}" --no-same-owner --no-same-permissions -C "${PARTIAL_DIR}"
printf '%s\n' "${GIT_SHA}" >"${PARTIAL_DIR}/DEPLOYED_COMMIT"

required_files=(
  "infra/compose.yaml"
  "infra/compose.production.yaml"
  "infra/compose.public-ip.yaml"
  "infra/compose.public-reuse.yaml"
  "infra/compose.release.yaml"
  "infra/ops/backup.sh"
  "apps/card-web/dist/index.html"
  "apps/admin-web/dist/index.html"
)
for relative_path in "${required_files[@]}"; do
  [[ -f "${PARTIAL_DIR}/${relative_path}" ]] || { fail "release is missing ${relative_path}"; exit 2; }
done

if find "${PARTIAL_DIR}" -type f \( -name '.env' -o -name '.env.*' \) ! -name '.env.example' -print -quit | grep -q .; then
  fail "release archive contains an environment file"
  exit 2
fi

grep -Eq '(src|href)="/c/' "${PARTIAL_DIR}/apps/card-web/dist/index.html" \
  || { fail "card web was not built for /c/"; exit 2; }
grep -Eq '(src|href)="/c/admin/' "${PARTIAL_DIR}/apps/admin-web/dist/index.html" \
  || { fail "admin web was not built for /c/admin/"; exit 2; }

mv -- "${PARTIAL_DIR}" "${RELEASE_DIR}"
chmod 755 "${RELEASE_DIR}/infra/ops/backup.sh" "${RELEASE_DIR}/infra/ops/deploy-production.sh"

export DEPLOY_SHA="${GIT_SHA}"
export COMPOSE_PARALLEL_LIMIT=1

compose_files=(
  -f "${RELEASE_DIR}/infra/compose.yaml"
  -f "${RELEASE_DIR}/infra/compose.production.yaml"
  -f "${RELEASE_DIR}/infra/compose.public-ip.yaml"
  -f "${RELEASE_DIR}/infra/compose.public-reuse.yaml"
  -f "${RELEASE_DIR}/infra/compose.release.yaml"
)

compose() {
  docker compose \
    --project-name "${COMPOSE_PROJECT}" \
    --env-file "${ENV_FILE}" \
    "${compose_files[@]}" \
    "$@"
}

running_image_id() {
  local service="$1"
  local container_id
  container_id="$(
    docker ps \
      --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" \
      --filter "label=com.docker.compose.service=${service}" \
      --format '{{.ID}}' |
      head -n 1
  )"
  [[ -n "${container_id}" ]] || return 1
  docker inspect --format '{{.Image}}' "${container_id}"
}

tag_rollback_image() {
  local source_service="$1"
  local rollback_repository="$2"
  local image_id
  image_id="$(running_image_id "${source_service}")" || return 1
  docker image tag "${image_id}" "${rollback_repository}:before-${STAMP}-${SHORT_SHA}"
  printf '%s\n' "${rollback_repository}:before-${STAMP}-${SHORT_SHA}"
}

log "capturing immutable rollback images"
ROLLBACK_API_IMAGE="$(tag_rollback_image api cf-ai-card-rollback-api)"
ROLLBACK_WORKER_IMAGE="$(tag_rollback_image worker cf-ai-card-rollback-worker)"
ROLLBACK_CARD_IMAGE="$(tag_rollback_image card-web cf-ai-card-rollback-card-web)"
ROLLBACK_ADMIN_IMAGE="$(tag_rollback_image admin-web cf-ai-card-rollback-admin-web)"
ROLLBACK_GATEWAY_IMAGE="$(tag_rollback_image gateway cf-ai-card-rollback-gateway)"

cat >"${ROLLBACK_OVERRIDE}" <<EOF
services:
  migrate:
    image: ${ROLLBACK_API_IMAGE}
  seed:
    image: ${ROLLBACK_API_IMAGE}
  index:
    image: ${ROLLBACK_API_IMAGE}
  api:
    image: ${ROLLBACK_API_IMAGE}
  worker:
    image: ${ROLLBACK_WORKER_IMAGE}
  beat:
    image: ${ROLLBACK_WORKER_IMAGE}
  card-web:
    image: ${ROLLBACK_CARD_IMAGE}
  admin-web:
    image: ${ROLLBACK_ADMIN_IMAGE}
  gateway:
    image: ${ROLLBACK_GATEWAY_IMAGE}
EOF
chmod 600 "${ROLLBACK_OVERRIDE}"

rollback_files=(
  -f "${RELEASE_DIR}/infra/compose.yaml"
  -f "${RELEASE_DIR}/infra/compose.production.yaml"
  -f "${RELEASE_DIR}/infra/compose.public-ip.yaml"
  -f "${RELEASE_DIR}/infra/compose.public-reuse.yaml"
  -f "${ROLLBACK_OVERRIDE}"
)

rollback_compose() {
  docker compose \
    --project-name "${COMPOSE_PROJECT}" \
    --env-file "${ENV_FILE}" \
    "${rollback_files[@]}" \
    "$@"
}

wait_for_service() {
  local service="$1"
  local timeout_seconds="${2:-900}"
  local deadline=$((SECONDS + timeout_seconds))
  local container_id state health

  while (( SECONDS < deadline )); do
    container_id="$(compose ps -q "${service}" 2>/dev/null || true)"
    if [[ -n "${container_id}" ]]; then
      state="$(docker inspect --format '{{.State.Status}}' "${container_id}" 2>/dev/null || true)"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}" 2>/dev/null || true)"
      if [[ "${state}" == "running" && ( "${health}" == "healthy" || "${health}" == "none" ) ]]; then
        return 0
      fi
      if [[ "${state}" == "exited" || "${health}" == "unhealthy" ]]; then
        compose logs --tail=100 "${service}" >&2 || true
        return 1
      fi
    fi
    sleep 5
  done

  compose logs --tail=100 "${service}" >&2 || true
  fail "service did not become healthy in ${timeout_seconds}s: ${service}"
}

rollback_application() {
  local rollback_failed=0

  log "rolling application containers back to pre-deployment images"
  if ! rollback_compose up -d --no-deps --no-build --force-recreate \
    api worker beat card-web admin-web gateway; then
    rollback_failed=1
  fi
  for service in api worker beat card-web admin-web gateway; do
    if ! wait_for_service "${service}" 300; then
      rollback_failed=1
    fi
  done
  if [[ -n "${PREVIOUS_LINK_TARGET}" && -d "${PREVIOUS_LINK_TARGET}" ]]; then
    ln -sfn "${PREVIOUS_LINK_TARGET}" "${CURRENT_LINK}.rollback"
    mv -Tf "${CURRENT_LINK}.rollback" "${CURRENT_LINK}"
  fi

  return "${rollback_failed}"
}

handle_failure() {
  local exit_code="$1"
  local reason="$2"

  trap - ERR HUP INT TERM
  log "deployment ${RELEASE_ID} failed (${reason}, exit code ${exit_code})"
  if (( DEPLOYMENT_CHANGED )); then
    if ! rollback_application; then
      log "automatic application rollback failed; production needs immediate operator attention"
    fi
  fi
  if [[ -n "${LATEST_BACKUP}" ]]; then
    log "pre-deployment backup retained at ${LATEST_BACKUP}; database restore is intentionally manual"
  fi
  exit "${exit_code}"
}

on_error() {
  local exit_code=$?
  handle_failure "${exit_code}" "command error"
}

on_signal() {
  local signal_name="$1"
  local exit_code="$2"
  handle_failure "${exit_code}" "received ${signal_name}"
}

trap on_error ERR
trap 'on_signal HUP 129' HUP
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM

log "validating production Compose graph"
compose config --quiet

log "creating a fresh PostgreSQL and object-storage backup"
sudo env \
  APP_ROOT="${RELEASE_DIR}" \
  ENV_FILE="${ENV_FILE}" \
  BACKUP_ROOT="${BACKUP_ROOT}" \
  COMPOSE_PROJECT="${COMPOSE_PROJECT}" \
  "${RELEASE_DIR}/infra/ops/backup.sh" </dev/null
LATEST_BACKUP="$(
  sudo find "${BACKUP_ROOT}/daily" -mindepth 1 -maxdepth 1 -type d ! -name '*.partial' -print |
    sort |
    tail -n 1
)"
[[ -n "${LATEST_BACKUP}" ]] || fail "backup script did not create a backup directory"
sudo test -s "${LATEST_BACKUP}/postgres.dump" || fail "PostgreSQL backup is empty"
sudo sh -c "cd '$LATEST_BACKUP' && sha256sum --check SHA256SUMS"

log "building versioned application images serially"
compose build api worker card-web admin-web gateway

log "running database migration"
compose run --rm --no-deps migrate

log "refreshing published seed data and embeddings"
compose run --rm --no-deps seed
compose run --rm --no-deps index

DEPLOYMENT_CHANGED=1

log "switching API and background services"
compose up -d --no-deps --force-recreate api worker beat
for service in api worker beat; do
  wait_for_service "${service}" 900
done

log "switching web applications"
compose up -d --no-deps --force-recreate card-web admin-web
for service in card-web admin-web; do
  wait_for_service "${service}" 300
done

log "switching gateway"
compose up -d --no-deps --force-recreate gateway
wait_for_service gateway 300

log "checking public routes"
curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 --max-time 15 \
  "${HEALTH_BASE_URL}/tuotu" >/dev/null
curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 --max-time 15 \
  "${HEALTH_BASE_URL}/api/v1/health/live" >/dev/null
curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 --max-time 15 \
  "${HEALTH_BASE_URL}/api/v1/health/ready" >/dev/null

log "activating release and repairing the backup timer"
ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}.next"
mv -Tf "${CURRENT_LINK}.next" "${CURRENT_LINK}"
sudo install -m 0644 \
  "${RELEASE_DIR}/infra/ops/shuzimingpian-backup.service" \
  /etc/systemd/system/shuzimingpian-backup.service
sudo install -m 0644 \
  "${RELEASE_DIR}/infra/ops/shuzimingpian-backup.timer" \
  /etc/systemd/system/shuzimingpian-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now shuzimingpian-backup.timer
sudo systemctl reset-failed shuzimingpian-backup.service || true

printf '%s\n' "${GIT_SHA}" >"${STATE_DIR}/deployed-sha"
printf '%s\n' "${RELEASE_DIR}" >"${STATE_DIR}/current-release"
printf '%s\n' "${LATEST_BACKUP}" >"${STATE_DIR}/last-predeploy-backup"

DEPLOYMENT_CHANGED=0
trap - ERR HUP INT TERM

log "pruning old GitHub-created releases"
mapfile -t github_releases < <(
  find "${RELEASES_DIR}" -mindepth 1 -maxdepth 1 -type d -name '*-github-*' -print |
    sort -r
)
for (( index=KEEP_RELEASES; index<${#github_releases[@]}; index++ )); do
  [[ "${github_releases[index]}" == "${RELEASE_DIR}" ]] || rm -rf -- "${github_releases[index]}"
done

for image_repository in \
  cf-ai-card-prod-api \
  cf-ai-card-prod-worker \
  cf-ai-card-prod-card-web \
  cf-ai-card-prod-admin-web \
  cf-ai-card-prod-gateway; do
  mapfile -t old_tags < <(
    docker image ls "${image_repository}" --format '{{.Tag}}' |
      grep -E '^[0-9a-f]{40}$' |
      tail -n "+$((KEEP_RELEASES + 1))" || true
  )
  for old_tag in "${old_tags[@]}"; do
    docker image rm "${image_repository}:${old_tag}" >/dev/null 2>&1 || true
  done
done

log "pruning obsolete rollback image tags"
for rollback_repository in \
  cf-ai-card-rollback-api \
  cf-ai-card-rollback-worker \
  cf-ai-card-rollback-card-web \
  cf-ai-card-rollback-admin-web \
  cf-ai-card-rollback-gateway; do
  mapfile -t rollback_tags < <(
    docker image ls "${rollback_repository}" --format '{{.Tag}}' |
      grep -E '^before-' |
      sort -r || true
  )
  kept_tags=0
  for rollback_tag in "${rollback_tags[@]}"; do
    if [[ "${rollback_tag}" =~ ^before-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] \
      && (( kept_tags < KEEP_RELEASES )); then
      kept_tags=$((kept_tags + 1))
      continue
    fi
    docker image rm "${rollback_repository}:${rollback_tag}" >/dev/null 2>&1 || true
  done
done

log "deployment completed: ${RELEASE_ID} (${GIT_SHA})"
