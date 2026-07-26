#!/usr/bin/env bash
# Helper: run docker / docker-compose with correct paths in Jenkins.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export DOCKER="${DOCKER:-/usr/local/bin/docker}"
export DOCKER_COMPOSE="${DOCKER_COMPOSE:-/usr/local/bin/docker-compose}"
exec "$@"
