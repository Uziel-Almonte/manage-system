#!/usr/bin/env bash
# Expose Flask + Keycloak on the public internet via Cloudflare quick tunnels
# (trycloudflare.com) so a demo can be reached without VPN or your own domain.
#
# Usage:
#   bash scripts/cloudflare-tunnel.sh          # start tunnels + reconfigure OAuth
#   bash scripts/cloudflare-tunnel.sh stop     # tear down tunnels + restore localhost
#   bash scripts/cloudflare-tunnel.sh status   # show URLs if running
#
# Requirements: Docker stack up (web + keycloak; also grafana if you want it
# tunneled — it's optional and tunneled automatically if it's already running).
# curl, python3 required.
# cloudflared is downloaded to .tools/ if missing (no Cloudflare account needed).
#
# localhost:5000 / localhost:8080 keep working the entire time this is running,
# and are the ONLY thing that works again once you run "stop" — nothing here
# permanently repoints the app away from localhost.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STATE_DIR="${ROOT_DIR}/.cloudflare-tunnel"
TOOLS_DIR="${ROOT_DIR}/.tools"
ENV_FILE="${ROOT_DIR}/.env.cloudflare"
CLOUDFLARED="${CLOUDFLARED:-${TOOLS_DIR}/cloudflared}"
COMPOSE="${DOCKER_COMPOSE:-docker compose}"

mkdir -p "$STATE_DIR" "$TOOLS_DIR"

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

ensure_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    CLOUDFLARED="$(command -v cloudflared)"
    return
  fi
  if [[ -x "$CLOUDFLARED" ]]; then
    return
  fi
  log "Downloading cloudflared to ${CLOUDFLARED}..."
  local url arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" ;;
    aarch64|arm64) url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64" ;;
    *) die "Unsupported architecture: $arch (install cloudflared manually)" ;;
  esac
  curl -fsSL "$url" -o "$CLOUDFLARED"
  chmod +x "$CLOUDFLARED"
}

wait_local() {
  local name="$1" url="$2" attempts="${3:-60}"
  log "Waiting for ${name} (${url})..."
  local i
  for i in $(seq 1 "$attempts"); do
    if curl -sf -o /dev/null "$url"; then
      echo "OK  ${name}"
      return 0
    fi
    sleep 2
  done
  die "${name} not reachable at ${url}. Start the stack first: docker compose up -d web keycloak"
}

start_one_tunnel() {
  local name="$1" target="$2"
  local log_file="${STATE_DIR}/${name}.log"
  local pid_file="${STATE_DIR}/${name}.pid"
  local url_file="${STATE_DIR}/${name}.url"

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    log "Tunnel ${name} already running (pid $(cat "$pid_file"))"
    return 0
  fi

  : >"$log_file"
  "$CLOUDFLARED" tunnel --no-autoupdate --url "$target" >"$log_file" 2>&1 &
  echo $! >"$pid_file"

  local i url=""
  for i in $(seq 1 45); do
    url="$(grep -Eo 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$log_file" | head -1 || true)"
    if [[ -n "$url" ]]; then
      echo "$url" >"$url_file"
      log "${name} public URL: ${url}"
      return 0
    fi
    if ! kill -0 "$(cat "$pid_file")" 2>/dev/null; then
      tail -n 40 "$log_file" >&2 || true
      die "cloudflared for ${name} exited early"
    fi
    sleep 1
  done
  tail -n 40 "$log_file" >&2 || true
  die "Timed out waiting for ${name} trycloudflare.com URL"
}

stop_tunnels() {
  local name pid_file
  for name in flask keycloak grafana; do
    pid_file="${STATE_DIR}/${name}.pid"
    if [[ -f "$pid_file" ]]; then
      local pid
      pid="$(cat "$pid_file")"
      if kill -0 "$pid" 2>/dev/null; then
        log "Stopping ${name} tunnel (pid ${pid})"
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
      fi
      rm -f "$pid_file"
    fi
  done
}

# Update the Keycloak "flask-backend" client so BOTH the given external URLs
# AND localhost keep being valid callback/logout targets at the same time.
# This is what lets localhost:5000 keep working while a tunnel is active, and
# is exactly what's left behind (localhost-only) once the tunnel is stopped.
configure_keycloak_client() {
  local flask_url="$1"
  local kc_url="$2"
  local callback="${flask_url%/}/auth/callback"

  log "Updating Keycloak client flask-backend redirect URIs -> ${callback} (+ localhost)"

  $COMPOSE exec -T \
    -e KC_ADMIN="${KEYCLOAK_USER:-admin}" \
    -e KC_ADMIN_PASSWORD="${KEYCLOAK_PASSWORD:-admin}" \
    -e CALLBACK="$callback" \
    -e FLASK_URL="$flask_url" \
    keycloak bash -ec '
    /opt/keycloak/bin/kcadm.sh config credentials \
      --server http://localhost:8080 \
      --realm master \
      --user "$KC_ADMIN" \
      --password "$KC_ADMIN_PASSWORD"
    CID=$(/opt/keycloak/bin/kcadm.sh get clients -r inventory-realm -q clientId=flask-backend --fields id --format csv --noquotes | tail -1)
    test -n "$CID"

    # Allow both http and https callback variants (ProxyFix / scheme quirks).
    HTTPS_CB="${CALLBACK/http:/https:}"
    HTTP_CB="${CALLBACK/https:/http:}"
    HTTPS_ROOT="${FLASK_URL/http:/https:}"
    HTTP_ROOT="${FLASK_URL/https:/http:}"

    # Keycloak post-logout URIs are "##"-separated; keep both the public URL
    # and localhost valid at all times so neither ever breaks the other.
    POST_LOGOUT="${HTTPS_ROOT%/}/*##${HTTPS_ROOT%/}/##${HTTP_ROOT%/}/*##${HTTP_ROOT%/}/##http://localhost:5000/*##http://localhost:5000/"

    /opt/keycloak/bin/kcadm.sh update "clients/$CID" -r inventory-realm \
      -s "redirectUris=[\"$HTTP_CB\",\"$HTTPS_CB\",\"http://localhost:5000/auth/callback\"]" \
      -s "webOrigins=[\"$FLASK_URL\",\"http://localhost:5000\",\"*\"]" \
      -s "attributes.\"post.logout.redirect.uris\"=$POST_LOGOUT"
  '
}

write_env_cloudflare() {
  local flask_url="$1"
  local kc_url="$2"
  cat >"$ENV_FILE" <<EOF
# Generated by scripts/cloudflare-tunnel.sh — do not commit
FLASK_PUBLIC_URL=${flask_url}
KEYCLOAK_PUBLIC_URL=${kc_url}
KC_HOSTNAME_URL=${kc_url}
KC_HOSTNAME_ADMIN_URL=${kc_url}
KC_PROXY_HEADERS=xforwarded
KEYCLOAK_ISSUER=${kc_url}/realms/inventory-realm
KEYCLOAK_AUTHORIZE_URL=${kc_url}/realms/inventory-realm/protocol/openid-connect/auth
KEYCLOAK_LOGOUT_BASE=${kc_url}/realms/inventory-realm/protocol/openid-connect/logout
EOF
  log "Wrote ${ENV_FILE}"
}

apply_public_config() {
  local flask_url="$1"
  local kc_url="$2"
  write_env_cloudflare "$flask_url" "$kc_url"

  log "Applying public hostnames to Keycloak + Flask (restart, no rebuild)..."
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  # Recreate only if config actually changed (no --force-recreate): on small
  # machines, unconditionally recreating every container here has previously
  # caused the app to crash under memory pressure and serve 502s.
  $COMPOSE --env-file .env --env-file "$ENV_FILE" up -d --no-deps keycloak web
  $COMPOSE --env-file .env --env-file "$ENV_FILE" restart keycloak web

  wait_local "Keycloak (local port)" "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration" 90
  wait_local "Flask (local port)" "http://localhost:5000/auth/login-page" 60

  sleep 3
  configure_keycloak_client "$flask_url" "$kc_url"

  if [[ -f scripts/prepare-keycloak-e2e.sh ]]; then
    log "Ensuring demo users (password123)..."
    COMPOSE_FILE=docker-compose.yml bash scripts/prepare-keycloak-e2e.sh || true
  fi
}

restore_localhost() {
  log "Restoring localhost-only Keycloak / Flask configuration..."
  rm -f "$ENV_FILE"
  unset KC_HOSTNAME_URL KC_HOSTNAME_ADMIN_URL KC_PROXY_HEADERS KEYCLOAK_ISSUER \
    KEYCLOAK_AUTHORIZE_URL KEYCLOAK_LOGOUT_BASE FLASK_PUBLIC_URL KEYCLOAK_PUBLIC_URL || true

  $COMPOSE --env-file .env up -d --no-deps keycloak web
  $COMPOSE --env-file .env restart keycloak web

  wait_local "Keycloak (local port)" "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration" 90
  wait_local "Flask (local port)" "http://localhost:5000/auth/login-page" 60

  if [[ -f .env ]]; then set -a; source .env; set +a; fi
  configure_keycloak_client "http://localhost:5000" "http://localhost:8080" || true
  log "Restored. Local app: http://localhost:5000 (fully independent of the tunnel now)"
}

print_status() {
  local flask_url kc_url grafana_url
  flask_url="$(cat "${STATE_DIR}/flask.url" 2>/dev/null || true)"
  kc_url="$(cat "${STATE_DIR}/keycloak.url" 2>/dev/null || true)"
  grafana_url="$(cat "${STATE_DIR}/grafana.url" 2>/dev/null || true)"
  echo ""
  echo "========== Cloudflare tunnel status =========="
  if [[ -n "$flask_url" ]]; then
    echo "  App (share this):     ${flask_url}"
    echo "  Login page:           ${flask_url}/auth/login-page"
  else
    echo "  App tunnel:           (not running)"
  fi
  if [[ -n "$kc_url" ]]; then
    echo "  Keycloak (public):    ${kc_url}"
  else
    echo "  Keycloak tunnel:      (not running)"
  fi
  if [[ -n "$grafana_url" ]]; then
    echo "  Grafana (public):     ${grafana_url}"
    echo "                        login required -> \${GRAFANA_ADMIN_USER:-admin} / \${GRAFANA_ADMIN_PASSWORD:-admin} (see .env)"
  else
    echo "  Grafana tunnel:       (not running — start 'grafana' in Docker first if you want it)"
  fi
  echo ""
  echo "  Local app (always works, tunnel or not): http://localhost:5000"
  echo ""
  echo "  Demo login: kratos_boss / password123  (manager)"
  echo "              alice_worker / password123 (employee)"
  echo ""
  echo "  Stop:  bash scripts/cloudflare-tunnel.sh stop"
  echo "=============================================="
}

cmd_start() {
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
  ensure_cloudflared
  wait_local "Flask" "http://localhost:5000/auth/login-page" 30
  wait_local "Keycloak" "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration" 30

  log "Starting Cloudflare quick tunnels (no account required)..."
  start_one_tunnel flask "http://127.0.0.1:5000"
  start_one_tunnel keycloak "http://127.0.0.1:8080"

  # Grafana is optional and not part of the OAuth setup — only tunnel it if it's
  # already up (docker compose up -d grafana). Never blocks the app/Keycloak tunnels.
  if curl -sf -o /dev/null "http://localhost:3000/api/health" 2>/dev/null; then
    start_one_tunnel grafana "http://127.0.0.1:3000"
  else
    log "Grafana not running locally on :3000 — skipping Grafana tunnel (this is fine)."
  fi

  local flask_url kc_url
  flask_url="$(cat "${STATE_DIR}/flask.url")"
  kc_url="$(cat "${STATE_DIR}/keycloak.url")"

  apply_public_config "$flask_url" "$kc_url"
  print_status

  log "Tunnels keep running in the background."
  log "PIDs: flask=$(cat "${STATE_DIR}/flask.pid") keycloak=$(cat "${STATE_DIR}/keycloak.pid")$( [[ -f "${STATE_DIR}/grafana.pid" ]] && echo " grafana=$(cat "${STATE_DIR}/grafana.pid")" )"
  log "localhost:5000 and localhost:8080 both still work normally while this is running."
}

cmd_stop() {
  stop_tunnels
  restore_localhost
  rm -f "${STATE_DIR}"/{flask,keycloak,grafana}.url "${STATE_DIR}"/{flask,keycloak,grafana}.log
  log "Cloudflare tunnels stopped. Only localhost works now — exactly as before this script ran."
}

cmd_status() {
  print_status
  local name pid_file
  for name in flask keycloak grafana; do
    pid_file="${STATE_DIR}/${name}.pid"
    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
      echo "  ${name} tunnel pid: $(cat "$pid_file") (running)"
    else
      echo "  ${name} tunnel: not running"
    fi
  done
}

case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  *)
    echo "Usage: $0 [start|stop|status]"
    exit 1
    ;;
esac
