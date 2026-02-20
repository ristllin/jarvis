#!/usr/bin/env bash
set -euo pipefail

if command -v npx >/dev/null 2>&1; then
  cd frontend && npx tsc --noEmit --pretty
elif docker inspect jarvis-jarvis-1 >/dev/null 2>&1; then
  docker exec jarvis-jarvis-1 bash -c "cd /frontend && npx tsc --noEmit --pretty"
else
  echo "SKIP: no node or running container for tsc"
  exit 0
fi
