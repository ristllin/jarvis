#!/bin/bash
# ─── JARVIS Build & Deploy Script ─────────────────────────────────────────
# Syncs code, rebuilds Docker image, and restarts all services.
# Usage:
#   ./build.sh              # Sync + rebuild + restart
#   ./build.sh --no-cache   # Force full rebuild (no Docker cache)
#   ./build.sh --sync-only  # Only sync jarvis/ → backend/jarvis/ (no build)
# ──────────────────────────────────────────────────────────────────────────
set -e

cd "$(dirname "$0")"

NO_CACHE=""
SYNC_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --no-cache)  NO_CACHE="--no-cache" ;;
        --sync-only) SYNC_ONLY=true ;;
    esac
done

# ── Step 1: Sync jarvis/ → backend/jarvis/ ────────────────────────────────
echo "=== Syncing jarvis/ → backend/jarvis/ ==="
rsync -av --delete \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='tests/' \
    --exclude='reload' \
    --exclude='_browser_part1.py' \
    --exclude='my_script.sh' \
    --exclude='deployment_guide.md' \
    --exclude='documentation.md' \
    --exclude='authentication.py' \
    jarvis/ backend/jarvis/
echo "=== Sync complete ==="

if [ "$SYNC_ONLY" = true ]; then
    echo "Sync-only mode — skipping build."
    exit 0
fi

# ── Step 2: Rebuild Docker image ──────────────────────────────────────────
echo ""
echo "=== Building Docker image ==="
docker compose build $NO_CACHE
echo "=== Build complete ==="

# ── Step 3: Restart services ─────────────────────────────────────────────
echo ""
echo "=== Restarting services ==="
docker compose down
docker compose up -d
echo ""
echo "=== JARVIS deployed ==="
echo "  Backend:   http://localhost:8000/api/status"
echo "  Frontend:  http://localhost:3000"
echo "  Dashboard: http://localhost (via nginx)"
echo ""
echo "Waiting for health check..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "  ✓ Backend healthy"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "  ✗ Backend did not become healthy in 60s — check: docker compose logs jarvis"
        exit 1
    fi
    sleep 1
done

VERSION=$(curl -sf http://localhost:8000/api/status 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','unknown'))" 2>/dev/null || echo "unknown")
echo "  Version: $VERSION"
echo ""
echo "Monitor logs: docker compose logs -f jarvis"
