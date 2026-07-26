#!/usr/bin/env bash
# HTTP helper for CI (supports Jenkins-in-Docker via host network).
ci_curl() {
  local docker="${DOCKER:-/usr/local/bin/docker}"

  if [[ "${CI_WAIT_USE_HOST_NETWORK:-}" == "1" ]]; then
    "$docker" run --rm --network host curlimages/curl:8.5.0 -fsSL "$@"
  else
    curl -fsSL "$@"
  fi
}

ci_http_ok() {
  local url="$1"
  ci_curl "$url" >/dev/null 2>&1
}
