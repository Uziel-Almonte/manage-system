#!/usr/bin/env bash
# Prepare Keycloak test users for E2E and k6 (password + kratos profile).
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.ci.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

compose() {
  if [[ -n "$COMPOSE_PROJECT" ]]; then
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" "$@"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

KC_ADMIN="${KEYCLOAK_ADMIN:-${KEYCLOAK_USER:-admin}}"
KC_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-${KEYCLOAK_PASSWORD:-admin}}"

echo "==> Preparing Keycloak users via kcadm"
compose exec -T \
  -e KC_ADMIN="$KC_ADMIN" \
  -e KC_ADMIN_PASSWORD="$KC_ADMIN_PASSWORD" \
  keycloak bash -c '
  /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user "$KC_ADMIN" \
    --password "$KC_ADMIN_PASSWORD"
  KRATOS_ID=$(/opt/keycloak/bin/kcadm.sh get users -r inventory-realm -q username=kratos_boss --fields id --format csv --noquotes | tail -1)
  /opt/keycloak/bin/kcadm.sh update users/$KRATOS_ID -r inventory-realm \
    -s firstName=Kratos \
    -s lastName=Boss \
    -s email=kratos@company.com \
    -s emailVerified=true
  for user in alice_worker kratos_boss; do
    /opt/keycloak/bin/kcadm.sh set-password \
      -r inventory-realm \
      --username "$user" \
      --new-password password123
  done
'
echo "==> Keycloak users ready"
