#!/usr/bin/env bash
# Wait until HTTP endpoints return success (2xx/3xx).
set -euo pipefail

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"
  local delay="${4:-2}"

  for ((i = 1; i <= attempts; i++)); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "OK  $name ($url)"
      return 0
    fi
    sleep "$delay"
  done

  echo "FAIL $name did not become ready: $url" >&2
  return 1
}

if [[ $# -gt 0 ]]; then
  while [[ $# -gt 0 ]]; do
    if [[ $# -ge 4 && "${3:-}" =~ ^[0-9]+$ && "${4:-}" =~ ^[0-9]+$ ]]; then
      wait_for_url "$1" "$2" "$3" "$4"
      shift 4
    else
      wait_for_url "$1" "$2"
      shift 2
    fi
  done
  exit 0
fi

wait_for_url "Flask" "http://localhost:5000/auth/login-page"
wait_for_url "Keycloak" "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration"
wait_for_url "Grafana" "http://localhost:3000/api/health"
wait_for_url "Prometheus" "http://localhost:9090/-/healthy"
wait_for_url "Alertmanager" "http://localhost:9093/-/healthy"
wait_for_url "Loki" "http://localhost:3100/ready"
wait_for_url "Tempo" "http://localhost:3200/ready"
wait_for_url "Alloy" "http://localhost:12345/-/healthy"
