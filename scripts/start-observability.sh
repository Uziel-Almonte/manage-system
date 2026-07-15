#!/usr/bin/env bash
# Start the full stack (app + observability). Same as: docker compose up -d --build
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Starting all services..."
docker compose up -d --build

echo "==> Waiting for Grafana (http://localhost:3000)..."
for _ in $(seq 1 40); do
  if curl -sf http://localhost:3000/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

echo ""
echo "App:"
echo "  Flask:         http://localhost:5000"
echo "  Keycloak:      http://localhost:8080"
echo ""
echo "Observability:"
echo "  Grafana:       http://localhost:3000"
echo "  Prometheus:    http://localhost:9090"
echo "  Tempo API:     http://localhost:3200"
echo "  Loki:          http://localhost:3100"
echo "  Alertmanager:  http://localhost:9093"
echo "  Alloy UI:      http://localhost:12345"
