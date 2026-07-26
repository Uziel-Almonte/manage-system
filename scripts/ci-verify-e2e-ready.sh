#!/usr/bin/env bash
# Verify CI services from inside the compose network (avoids Jenkins localhost:8080 clash).
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.ci.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:?COMPOSE_PROJECT is required}"

if [[ -n "${DOCKER_COMPOSE:-}" ]]; then
  compose() { "$DOCKER_COMPOSE" -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" "$@"; }
else
  compose() { docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" "$@"; }
fi

echo "==> Checking Keycloak realm via compose network"
compose exec -T web python scripts/wait-for-keycloak-realm.py

echo "==> Checking Flask login page via compose network"
compose exec -T web python -c "
import urllib.request
urllib.request.urlopen('http://127.0.0.1:5000/auth/login-page', timeout=5)
print('OK  Flask login page')
"
