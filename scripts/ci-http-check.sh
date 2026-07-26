#!/usr/bin/env bash
# HTTP helper for CI (Jenkins-in-Docker reaches host services via host.docker.internal).
ci_resolve_url() {
  local url="$1"
  if [[ "${CI_WAIT_USE_HOST_NETWORK:-}" == "1" ]]; then
    echo "${url//localhost/host.docker.internal}"
  else
    echo "$url"
  fi
}

ci_curl() {
  local resolved=()
  for arg in "$@"; do
    resolved+=("$(ci_resolve_url "$arg")")
  done
  curl "${resolved[@]}"
}

ci_http_ok() {
  local url
  url="$(ci_resolve_url "$1")"
  curl -fsSL "$url" >/dev/null 2>&1
}
