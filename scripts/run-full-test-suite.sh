#!/usr/bin/env bash
# Run the complete test matrix locally (matches Jenkins / GitHub Actions).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR"
export FLASK_APP=app.main
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:ci_password@db:5432/inventory_db}"
COMPOSE_CI="${COMPOSE_CI:-docker-compose.ci.yml}"
COMPOSE_FULL="${COMPOSE_FULL:-docker-compose.yml}"
PROJECT_CI="${PROJECT_CI:-manage-system-test-ci}"
RUN_E2E="${RUN_E2E:-true}"
RUN_STACK="${RUN_STACK:-true}"
RUN_K6="${RUN_K6:-true}"

compose_ci() {
  docker compose -f "$COMPOSE_CI" -p "$PROJECT_CI" "$@"
}

compose_full() {
  docker compose -f "$COMPOSE_FULL" "$@"
}

cleanup() {
  compose_ci down -v --remove-orphans 2>/dev/null || true
  compose_full down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

compose_network() {
  compose_ci ps -q db | head -1 | xargs -r docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}'
}

python_runner() {
  docker run --rm \
    -v "$ROOT_DIR:/app" -w /app \
    -e PYTHONPATH=/app -e FLASK_APP=app.main -e DATABASE_URL="$DATABASE_URL" \
    --network host \
    python:3.12-slim \
    bash -lc "pip install -q -r requirements.txt && python3 $(printf '%q ' "$@")"
}

db_python_runner() {
  local net
  net="$(compose_network)"
  docker run --rm \
    -v "$ROOT_DIR:/app" -w /app \
    -e PYTHONPATH=/app -e FLASK_APP=app.main \
    -e DATABASE_URL=postgresql://postgres:ci_password@db:5432/inventory_db \
    --network "$net" \
    python:3.12-slim \
    bash -lc "pip install -q -r requirements.txt && python3 $(printf '%q ' "$@")"
}

echo "========== 1/8 Build =========="
docker build -t manage-system:local .

echo "========== 2/8 Unit tests =========="
python_runner -m pytest tests/test_products.py tests/test_stock.py -v --tb=short

echo "========== 3/8 API / contract tests =========="
python_runner -m pytest tests/test_contract.py -v --tb=short

echo "========== 4/8 Data / migration tests =========="
compose_ci up -d db
until compose_ci exec -T db pg_isready -U postgres -d inventory_db >/dev/null 2>&1; do sleep 1; done
db_python_runner -m flask db upgrade
db_python_runner -m pytest tests/data/ -v --tb=short
compose_ci down -v

echo "========== 5/8 Coverage (non-E2E) =========="
compose_ci up -d db
until compose_ci exec -T db pg_isready -U postgres -d inventory_db >/dev/null 2>&1; do sleep 1; done
db_python_runner -m flask db upgrade
db_python_runner -m pytest tests/ -m "not e2e" --cov=app --cov-report=term-missing --tb=short
compose_ci down -v

echo "========== 6/8 Security (pip-audit) =========="
docker run --rm -v "$ROOT_DIR:/app" -w /app python:3.12-slim \
  bash -lc "pip install -q pip-audit && pip-audit -r requirements.txt"

if [[ "$RUN_E2E" == "true" ]]; then
  echo "========== 7/8 E2E tests =========="
  bash scripts/ci-free-host-ports.sh
  compose_ci up -d --build
  bash scripts/wait-for-services.sh \
    "Flask" "http://localhost:5000/auth/login-page" \
    "Keycloak" "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration"
  compose_ci exec -T web flask db upgrade
  COMPOSE_FILE="$COMPOSE_CI" COMPOSE_PROJECT="$PROJECT_CI" bash scripts/prepare-keycloak-e2e.sh

  if python3 -c "import playwright" 2>/dev/null; then
    python3 -m pytest tests/e2e -m e2e -v --tb=short
  else
    docker run --rm --network host \
      -v "$ROOT_DIR:/app" -w /app \
      -e PYTHONPATH=/app \
      -e E2E_BASE_URL=http://localhost:5000 \
      mcr.microsoft.com/playwright/python:v1.60.0-jammy \
      bash -lc "pip install -q -r requirements.txt && pytest tests/e2e -m e2e -v --tb=short"
  fi
  compose_ci down -v
fi

if [[ "$RUN_STACK" == "true" ]]; then
  echo "========== 8/8 Full stack + observability + k6 smoke =========="
  compose_full down -v --remove-orphans 2>/dev/null || true
  compose_full up -d --build
  bash scripts/wait-for-services.sh
  compose_full exec -T web flask db upgrade
  COMPOSE_FILE="$COMPOSE_FULL" bash scripts/prepare-keycloak-e2e.sh
  bash scripts/verify-stack.sh

  if [[ "$RUN_K6" == "true" ]]; then
    mkdir -p reports
    docker run --rm --network host \
      -v "$ROOT_DIR:/app" -w /app \
      -e BASE_URL=http://localhost:5000 \
      -e KEYCLOAK_URL=http://localhost:8080 \
      grafana/k6:0.53.0 run tests/k6/smoke-test.js
  fi
fi

echo ""
echo "Full test suite completed successfully."
