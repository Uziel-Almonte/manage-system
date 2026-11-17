#!/usr/bin/env bash
# Deploy the staging stack and run Playwright plus an OWASP ZAP baseline scan.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-manage-system-staging}"
STAGING_URL="${STAGING_URL:-http://localhost:5000}"

compose() {
  if [[ -n "${DOCKER_COMPOSE:-}" ]]; then
    "$DOCKER_COMPOSE" -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" "$@"
  elif command -v docker-compose >/dev/null 2>&1 && ! command -v docker >/dev/null 2>&1; then
    docker-compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" "$@"
  else
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" "$@"
  fi
}

if [[ ! -f .env ]]; then
  echo "==> No .env found. Creating one from .env.example for local staging."
  cp .env.example .env
  python3 - <<'PY'
from pathlib import Path
path = Path(".env")
text = path.read_text()
replacements = {
    "POSTGRES_PASSWORD=your_password_here": "POSTGRES_PASSWORD=staging_password",
    "postgresql://postgres:your_password_here@": "postgresql://postgres:staging_password@",
    "KEYCLOAK_USER=admin_username_here": "KEYCLOAK_USER=admin",
    "KEYCLOAK_PASSWORD=admin_password_here": "KEYCLOAK_PASSWORD=admin",
    "GRAFANA_ADMIN_PASSWORD=grafana_admin_password_here": "GRAFANA_ADMIN_PASSWORD=admin",
}
for old, new in replacements.items():
    text = text.replace(old, new)
if "FLASK_SECRET_KEY=" not in text:
    text += "\nFLASK_SECRET_KEY=staging-secret-change-me\n"
path.write_text(text)
PY
fi

mkdir -p security-reports reports

echo "==> Starting staging stack"
compose up -d --build

echo "==> Waiting for Flask and Keycloak"
bash scripts/wait-for-services.sh \
  "Flask" "${STAGING_URL}/auth/login-page" 90 5 \
  "Keycloak" "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration" 90 5

echo "==> Preparing Keycloak test users"
COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT="$COMPOSE_PROJECT" bash scripts/prepare-keycloak-e2e.sh

echo "==> Playwright end-to-end tests against ${STAGING_URL}"
export E2E_BASE_URL="$STAGING_URL"
export E2E_ALICE_USER=alice_worker
export E2E_ALICE_PASSWORD=password123
export E2E_MANAGER_USER=kratos_boss
export E2E_MANAGER_PASSWORD=password123
if python3 -c "import playwright" 2>/dev/null; then
  python3 -m pytest tests/e2e -m e2e -v --tb=short --junitxml=reports/junit-staging-e2e.xml
else
  docker run --rm --network host \
    -v "$ROOT_DIR:/app" -w /app \
    -e PYTHONPATH=/app \
    -e E2E_BASE_URL="$STAGING_URL" \
    -e E2E_ALICE_USER=alice_worker \
    -e E2E_ALICE_PASSWORD=password123 \
    -e E2E_MANAGER_USER=kratos_boss \
    -e E2E_MANAGER_PASSWORD=password123 \
    mcr.microsoft.com/playwright/python:v1.60.0-jammy \
    bash -lc "pip install -q -r requirements.txt && pytest tests/e2e -m e2e -v --tb=short --junitxml=reports/junit-staging-e2e.xml"
fi

echo "==> OWASP ZAP baseline against the staging web service"
mkdir -p security-reports
chmod 777 security-reports
set +e
compose --profile security run --rm zap
zap_status=$?
set -e
echo "$zap_status" > security-reports/staging-zap-exit-code.txt
if [[ "$zap_status" -eq 1 ]]; then
  echo "ZAP reported a failing alert. See security-reports/staging-zap-baseline.html"
  exit "$zap_status"
fi
if [[ "$zap_status" -ne 0 ]]; then
  echo "ZAP finished with status ${zap_status} (warnings). Report: security-reports/staging-zap-baseline.html"
fi

echo ""
echo "Staging is up at ${STAGING_URL}"
echo "E2E report: reports/junit-staging-e2e.xml"
echo "ZAP report: security-reports/staging-zap-baseline.html"
