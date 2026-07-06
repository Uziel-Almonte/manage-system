#!/usr/bin/env bash
# Run Day 32 security checks: OWASP ZAP baseline + pip-audit.
# Requires the app stack to be up (docker compose up -d).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p security-reports

echo "==> Ensuring web, db, and keycloak are running..."
docker compose up -d web db keycloak

echo "==> Waiting for Flask app..."
for _ in $(seq 1 30); do
  if curl -sf "${SECURITY_SCAN_TARGET:-http://localhost:5000}/auth/login-page" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Running OWASP ZAP baseline scan (target: ${SECURITY_SCAN_TARGET:-http://web:5000})..."
docker compose --profile security run --rm zap

echo "==> Running pip-audit on requirements.txt..."
docker compose --profile security run --rm pip-audit

echo ""
echo "Reports written to security-reports/:"
ls -la security-reports/
