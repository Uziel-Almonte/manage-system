#!/usr/bin/env bash
# Wait until HTTP endpoints return success (2xx/3xx).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/ci-http-check.sh"

CI_HOST="${CI_HOST:-localhost}"

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"
  local delay="${4:-2}"

  for ((i = 1; i <= attempts; i++)); do
    if ci_http_ok "$url"; then
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

wait_for_url "Flask" "http://${CI_HOST}:5000/auth/login-page"
wait_for_url "Keycloak" "http://${CI_HOST}:8080/realms/inventory-realm/.well-known/openid-configuration"
wait_for_url "Grafana" "http://${CI_HOST}:3000/api/health"
wait_for_url "Prometheus" "http://${CI_HOST}:9090/-/healthy"
wait_for_url "Alertmanager" "http://${CI_HOST}:9093/-/healthy"
wait_for_url "Loki" "http://${CI_HOST}:3100/ready"
wait_for_url "Tempo" "http://${CI_HOST}:3200/ready"
wait_for_url "Alloy" "http://${CI_HOST}:12345/-/healthy"
