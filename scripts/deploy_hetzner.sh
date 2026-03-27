#!/usr/bin/env bash
set -euo pipefail

# Deploy StreetGPT (app + MongoDB + HTTPS reverse proxy) to Hetzner via SSH.
# Prereqs:
# - SSH config alias "hetzner_streetgpt" is set and reachable (see ~/.ssh/config)
# - Remote server has Docker and Docker Compose v2 installed
# - Your local repo contains docker-compose.yml, Dockerfile, and Caddyfile
# - Your local .env holds all required env vars (will be copied securely)
#
# Usage:
#   scripts/deploy_hetzner.sh [remote_path]
#
# Example:
#   scripts/deploy_hetzner.sh /opt/streetgpt
#
# Notes:
# - The app is served through Caddy on ports 80/443. Streamlit itself stays
#   on the internal Docker network and is no longer exposed directly.
# - We DO NOT expose Mongo publicly by default in production.
# - The script copies .env with mode 600 on the server.

REMOTE_ALIAS=${REMOTE_ALIAS:-hetzner_streetgpt}
REMOTE_PATH=${1:-/opt/streetgpt}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)

# Files/dirs to exclude from rsync (source control, caches, local envs)
EXCLUDES=(
  ".git/"
  ".gitignore"
  "py-streetgpt/"
  "__pycache__/"
  ".venv/"
  ".env"            # handled separately
  ".streamlit/"     # not needed in container (we use env vars). Mount if you want.
  "*.log"
  "*.tmp"
)

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "[info] %s\n" "$*"; }
warn() { printf "\033[33m[warn]\033[0m %s\n" "$*"; }
fail() { printf "\033[31m[fail]\033[0m %s\n" "$*"; exit 1; }

bold "Deploying StreetGPT to ${REMOTE_ALIAS}:${REMOTE_PATH}"

# 1) Ensure remote path exists
info "Ensuring remote directory exists"
ssh "${REMOTE_ALIAS}" '
  set -euo pipefail
  REMOTE_USER="$(id -un)"
  REMOTE_GROUP="$(id -gn)"
  sudo mkdir -p '"${REMOTE_PATH}"'
  sudo chown -R "$REMOTE_USER:$REMOTE_GROUP" '"${REMOTE_PATH}"' || true
'

# 2) Rsync project (excluding heavy/local files)
info "Rsync project files"
RSYNC_EXCLUDES=()
for e in "${EXCLUDES[@]}"; do RSYNC_EXCLUDES+=( --exclude "$e" ); done
rsync -az --delete "${RSYNC_EXCLUDES[@]}" \
  --chmod=Du=rwx,Dg=rx,Do=rx,Fu=rw,Fg=r,Fo=r \
  "${PROJECT_ROOT}/" "${REMOTE_ALIAS}:${REMOTE_PATH}/"

# 3) Copy .env securely and set permissions
if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
  fail ".env not found at ${PROJECT_ROOT}/.env"
fi
info "Copy .env to server"
scp "${PROJECT_ROOT}/.env" "${REMOTE_ALIAS}:${REMOTE_PATH}/.env"
ssh "${REMOTE_ALIAS}" "chmod 600 '${REMOTE_PATH}/.env'"

# 4) On remote: pull/build and start containers
read -r -d '' REMOTE_CMD <<'EOF' || true
set -euo pipefail
cd "__REMOTE_PATH__"

# Ensure Docker Engine + Compose are installed
if ! command -v docker >/dev/null 2>&1; then
  echo "[remote] Docker not found. Installing Docker Engine + Compose..." >&2
  # Based on Docker official install for Debian/Ubuntu
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl gnupg lsb-release
  if [ ! -e /etc/apt/keyrings/docker.gpg ]; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
  fi
  echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Ensure SITE_HOST is present for the Caddy config. Prefer an explicit hostname
# in .env. If it is missing, or if it is just a raw IPv4 address, derive a
# browser-friendly sslip.io hostname from the server's public IPv4 address.
SITE_HOST="$(awk -F= '/^SITE_HOST=/{print $2; exit}' .env || true)"
PUBLIC_IP=""
if printf '%s' "${SITE_HOST}" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  PUBLIC_IP="${SITE_HOST}"
  SITE_HOST=""
fi
if [ -z "${PUBLIC_IP}" ]; then
  PUBLIC_IP="$(curl -4fsS https://api.ipify.org || true)"
fi
if [ -z "${PUBLIC_IP}" ]; then
  PUBLIC_IP="$(hostname -I | awk '{print $1}')"
fi
if [ -z "${PUBLIC_IP}" ]; then
  echo "[remote] Unable to determine the server IPv4 address. Set SITE_HOST in .env and rerun." >&2
  exit 1
fi
if [ -z "${SITE_HOST}" ]; then
  SITE_HOST="${PUBLIC_IP//./-}.sslip.io"
fi
if grep -q '^SITE_HOST=' .env; then
  sed -i "s/^SITE_HOST=.*/SITE_HOST=${SITE_HOST}/" .env
else
  printf '\nSITE_HOST=%s\n' "${SITE_HOST}" >> .env
fi

echo "[remote] Using SITE_HOST=${SITE_HOST}"

# choose docker compose shim (use sudo to avoid group issues in non-login shell)
if docker compose version >/dev/null 2>&1; then
  DC="sudo docker compose"
elif docker-compose version >/dev/null 2>&1; then
  DC="sudo docker-compose"
else
  echo "[remote] Docker Compose not available even after install" >&2; exit 1
fi

# ensure network/volumes exist implicitly by compose
$DC pull || true
$DC up -d --build

# prune old images (safe: dangling only)
docker image prune -f >/dev/null 2>&1 || true

# Wait for the HTTPS front door to come up on the configured host.
healthy=0
for _ in $(seq 1 45); do
  if curl -kfsS --connect-timeout 5 --resolve "${SITE_HOST}:443:127.0.0.1" "https://${SITE_HOST}/_stcore/health" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [ "${healthy}" -ne 1 ]; then
  echo "[remote] HTTPS health check failed for https://${SITE_HOST}/_stcore/health" >&2
  $DC ps >&2 || true
  $DC logs --tail=100 caddy app >&2 || true
  exit 1
fi

# print status
$DC ps
echo "[remote] HTTPS endpoint is ready at https://${SITE_HOST}/"
EOF

# Inject path into remote command and run
REMOTE_EXEC=$(printf "%s" "$REMOTE_CMD" | sed "s#__REMOTE_PATH__#${REMOTE_PATH//\/#}#g")

info "Building and starting containers on server"
ssh "${REMOTE_ALIAS}" "$REMOTE_EXEC"

bold "Deployment completed."

echo ""
bold "Post-deploy checks"
cat <<POST
- Verify app: https://<site-host>/
- Logs: ssh ${REMOTE_ALIAS} "docker compose -f ${REMOTE_PATH}/docker-compose.yml logs -f --tail=100"
- Mongo is not exposed publicly by default. Keep it that way in production.
POST
