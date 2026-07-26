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
  local args=("$@")
  local resolved=()
  local needs_host_header=false

  for arg in "${args[@]}"; do
    local next
    next="$(ci_resolve_url "$arg")"
    resolved+=("$next")
    if [[ "$next" == *":8080"* ]]; then
      needs_host_header=true
    fi
  done

  if [[ "${CI_WAIT_USE_HOST_NETWORK:-}" == "1" && "$needs_host_header" == "true" ]]; then
    curl -H "Host: localhost" "${resolved[@]}"
  else
    curl "${resolved[@]}"
  fi
}

ci_http_ok() {
  local url
  url="$(ci_resolve_url "$1")"
  if [[ "${CI_WAIT_USE_HOST_NETWORK:-}" == "1" && "$url" == *":8080"* ]]; then
    curl -fsSL -H "Host: localhost" "$url" >/dev/null 2>&1
  else
    curl -fsSL "$url" >/dev/null 2>&1
  fi
}
