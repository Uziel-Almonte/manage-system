#!/bin/bash
set -euo pipefail

# Allow the jenkins user to access the host Docker socket mounted at runtime.
if [ -S /var/run/docker.sock ]; then
  DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
  groupadd -g "${DOCKER_GID}" dockerhost 2>/dev/null || true
  usermod -aG dockerhost jenkins 2>/dev/null || true
fi

# Bind-mounted project repo (docker-compose .:/workspace)
git config --system --add safe.directory /workspace 2>/dev/null || true

exec /usr/bin/tini -- /usr/local/bin/jenkins.sh "$@"
