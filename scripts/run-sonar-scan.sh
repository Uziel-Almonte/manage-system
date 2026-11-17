#!/usr/bin/env bash
# Generate coverage and scan the project with a local SonarQube.
# Needs SONAR_TOKEN (create it in the SonarQube UI: My Account > Security).
# Does not touch the app stack or its volumes.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SONAR_HOST_URL="${SONAR_HOST_URL:-http://localhost:9000}"
: "${SONAR_TOKEN:?Set SONAR_TOKEN first (export SONAR_TOKEN=...)}"

if ! curl -fs "$SONAR_HOST_URL/api/system/status" | grep -q '"status":"UP"'; then
  echo "SonarQube is not up at $SONAR_HOST_URL. Start it with:" >&2
  echo "  docker compose -f docker-compose.sonar.yml -p manage-system-sonar up -d" >&2
  exit 1
fi

if [[ "${SKIP_COVERAGE:-false}" != "true" ]]; then
  echo "==> Coverage (non-E2E, SQLite/unit + contract tests)"
  docker run --rm -v "$ROOT_DIR:/app" -w /app \
    -e PYTHONPATH=/app -e FLASK_APP=app.main \
    python:3.12-slim \
    bash -lc "pip install -q -r requirements.txt && pytest tests/test_products.py tests/test_stock.py tests/test_contract.py --cov=app --cov-report=xml:coverage.xml -q" \
    || echo "WARN: coverage step failed, scanning without fresh coverage"
fi

echo "==> SonarQube scan"
docker run --rm --network host \
  -v "$ROOT_DIR:/usr/src" \
  -e SONAR_HOST_URL="$SONAR_HOST_URL" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  sonarsource/sonar-scanner-cli

echo "Done. Results: $SONAR_HOST_URL/dashboard?id=manage-system"
