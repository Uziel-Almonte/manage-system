#!/usr/bin/env bash
# Stop containers blocking CI host ports (leftover dev stacks, failed builds).
set -euo pipefail

COMPOSE_CI="${COMPOSE_CI:-docker-compose.ci.yml}"
PORTS="${CI_PORTS:-5432 8080 5000}"
KEEP_PROJECTS="${CI_KEEP_PROJECTS:-}"

keep_project() {
  local proj="$1"
  [[ -z "$KEEP_PROJECTS" ]] && return 1
  local keep
  for keep in $KEEP_PROJECTS; do
    [[ "$proj" == "$keep" || "$proj" == "${keep}-data" || "$proj" == "${keep}-cov" ]] && return 0
  done
  return 1
}

for net in $(docker network ls --format '{{.Name}}' | grep -E '^manage-ci-[0-9]+(-[a-z]+)?_default$' || true); do
  proj="${net%_default}"
  if keep_project "$proj"; then
    continue
  fi
  echo "==> Removing stale compose project: $proj"
  docker compose -f "$COMPOSE_CI" -p "$proj" down -v --remove-orphans 2>/dev/null || true
done

for port in $PORTS; do
  while read -r cid proj; do
    [[ -z "$cid" ]] && continue
    if keep_project "$proj"; then
      continue
    fi
    echo "==> Stopping container $cid (project=${proj:-unknown}) on port $port"
    docker stop "$cid" >/dev/null 2>&1 || true
  done < <(docker ps --filter "publish=$port" --format '{{.ID}} {{.Label "com.docker.compose.project"}}' 2>/dev/null || true)
done
