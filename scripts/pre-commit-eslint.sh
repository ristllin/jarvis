#!/usr/bin/env bash
set -euo pipefail

# pre-commit passes absolute paths; eslint needs to run from frontend/
# Convert absolute paths to relative paths from frontend/
FRONTEND_DIR="$(cd "$(dirname "$0")/../frontend" && pwd)"
ARGS=()
for f in "$@"; do
  if [[ "$f" == /* ]]; then
    ARGS+=("$f")
  else
    ARGS+=("$(pwd)/$f")
  fi
done

if command -v npx >/dev/null 2>&1; then
  cd "$FRONTEND_DIR" && npx eslint --max-warnings 35 "${ARGS[@]}"
elif docker inspect jarvis-jarvis-1 >/dev/null 2>&1; then
  docker exec jarvis-jarvis-1 bash -c "cd /frontend && npx eslint --max-warnings 35 ${ARGS[*]}"
else
  echo "SKIP: no node or running container for eslint"
  exit 0
fi
