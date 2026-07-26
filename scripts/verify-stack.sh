#!/usr/bin/env bash
# Health-check every service in the full stack + provisioned Grafana dashboards.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CI_HOST="${CI_HOST:-localhost}"
json_query() {
  python3 -c "$1"
}

echo "==> Waiting for core services"
bash scripts/wait-for-services.sh

echo "==> Flask metrics endpoint"
METRICS_BODY="$(curl -sf "http://${CI_HOST}:5000/metrics")"
if ! grep -q "flask_http_request" <<<"$METRICS_BODY"; then
  echo "FAIL Flask /metrics missing prometheus metrics" >&2
  exit 1
fi
echo "OK  Flask /metrics exposes prometheus metrics"

echo "==> Prometheus targets"
TARGETS_JSON="$(curl -sf "http://${CI_HOST}:9090/api/v1/targets")"
for job in flask node_exporter prometheus; do
  UP_COUNT="$(TARGETS_JSON="$TARGETS_JSON" JOB="$job" json_query '
import json, os
data = json.loads(os.environ["TARGETS_JSON"])
job = os.environ["JOB"]
print(sum(1 for t in data["data"]["activeTargets"] if t["labels"].get("job") == job and t["health"] == "up"))
')"
  if [[ "$UP_COUNT" -lt 1 ]]; then
    echo "FAIL Prometheus target job=$job is not UP" >&2
    exit 1
  fi
  echo "OK  Prometheus job=$job is UP"
done

echo "==> Grafana dashboards (provisioned)"
DASHBOARDS="$(curl -sf "http://${CI_HOST}:3000/api/search?type=dash-db")"
DASH_COUNT="$(DASHBOARDS="$DASHBOARDS" json_query 'import json, os; print(len(json.loads(os.environ["DASHBOARDS"])))')"
if [[ "$DASH_COUNT" -lt 4 ]]; then
  echo "FAIL Expected at least 4 Grafana dashboards, found $DASH_COUNT" >&2
  exit 1
fi

for title in \
  "Aplicación - Latencia, Throughput y Errores" \
  "Infraestructura - CPU, Memoria y DB Pool" \
  "Negocio - Productos y Movimientos de Stock" \
  "Seguridad - Fallos de Autenticación y Tokens"
do
  FOUND="$(TITLE="$title" DASHBOARDS="$DASHBOARDS" json_query '
import json, os
title = os.environ["TITLE"]
dashboards = json.loads(os.environ["DASHBOARDS"])
print(any(d.get("title") == title for d in dashboards))
')"
  if [[ "$FOUND" != "True" ]]; then
    echo "FAIL Missing Grafana dashboard: $title" >&2
    exit 1
  fi
  echo "OK  Dashboard: $title"
done

echo "==> Grafana datasources"
DS_COUNT="$(curl -sf "http://${CI_HOST}:3000/api/datasources" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
if [[ "$DS_COUNT" -lt 3 ]]; then
  echo "FAIL Expected Prometheus, Loki, and Tempo datasources (found $DS_COUNT)" >&2
  exit 1
fi
echo "OK  Grafana datasources ($DS_COUNT)"

echo "==> Keycloak token grant (kratos_boss)"
TOKEN_RESPONSE="$(curl -sf -X POST "http://${CI_HOST}:8080/realms/inventory-realm/protocol/openid-connect/token" \
  -d "client_id=flask-backend" \
  -d "grant_type=password" \
  -d "username=kratos_boss" \
  -d "password=password123" \
  -d "scope=openid")"
if ! echo "$TOKEN_RESPONSE" | python3 -c 'import json,sys; json.load(sys.stdin)["access_token"]' >/dev/null 2>&1; then
  echo "FAIL Keycloak password grant for kratos_boss" >&2
  echo "$TOKEN_RESPONSE" >&2
  exit 1
fi
echo "OK  Keycloak password grant"

echo "==> API smoke (authenticated GET /api/products)"
ACCESS_TOKEN="$(echo "$TOKEN_RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
API_STATUS="$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://${CI_HOST}:5000/api/products")"
if [[ "$API_STATUS" != "200" ]]; then
  echo "FAIL GET /api/products returned HTTP $API_STATUS" >&2
  exit 1
fi
echo "OK  GET /api/products"

echo ""
echo "All stack checks passed."
