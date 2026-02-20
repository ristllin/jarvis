#!/bin/bash
# ─── JARVIS Entrypoint ─────────────────────────────────────────────────────
# This script handles:
#   1. Restoring self-modified code from /data/code/ (persisted volume)
#   2. Initializing git repo with baseline commit
#   3. Health-checking after code restore (auto-revert on broken code)
#   4. Starting the frontend + backend
#   5. Monitoring backend health, auto-reverting bad self-modifications
# ───────────────────────────────────────────────────────────────────────────
set -e

CODE_BACKUP="/data/code"
HEALTH_FLAG="/data/code/.healthy"
REVERT_FLAG="/data/code/.needs_revert"

echo "=== JARVIS Entrypoint ==="

# ── 0. Image version tracking ─────────────────────────────────────────────
# Hash ALL Python files in /app to detect any image update
IMAGE_HASH=$(find /app -name "*.py" -type f | sort | xargs md5sum 2>/dev/null | md5sum | cut -d' ' -f1)
STORED_HASH=""
if [ -f "/data/code/.image_hash" ]; then
    STORED_HASH=$(cat /data/code/.image_hash)
fi

# ── 1. Git identity ────────────────────────────────────────────────────────
git config --global user.name "${GIT_USER_NAME:-JARVIS}"
git config --global user.email "${GIT_USER_EMAIL:-jarvis.bot.g.d@gmail.com}"

# Store git credentials if a token is provided
if [ -n "$GITHUB_TOKEN" ]; then
    git config --global credential.helper store
    echo "https://${GIT_USER_NAME:-JARVIS}:${GITHUB_TOKEN}@github.com" > /root/.git-credentials
    echo "[entrypoint] GitHub token configured for push/pull"
fi

# ── 1b. Ensure GitHub remote is always configured ─────────────────────────
_ensure_remote() {
    local dir="$1"
    if [ -d "$dir/.git" ] && [ -n "$GITHUB_REPO" ] && echo "$GITHUB_REPO" | grep -qv "REPLACE"; then
        cd "$dir"
        git remote add origin "$GITHUB_REPO" 2>/dev/null || git remote set-url origin "$GITHUB_REPO"
    fi
}

# ── 2. Initialize code backup in /data/code/ ──────────────────────────────
mkdir -p "$CODE_BACKUP/backend" "$CODE_BACKUP/frontend"

if [ ! -d "$CODE_BACKUP/backend/.git" ]; then
    echo "[entrypoint] First boot — seeding code backup from image"
    cp -a /app/. "$CODE_BACKUP/backend/"
    cp -a /frontend/. "$CODE_BACKUP/frontend/"

    cd "$CODE_BACKUP/backend"
    # Create .gitignore for cleanliness
    cat > .gitignore << 'GITIGNORE'
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
GITIGNORE
    git init
    git add -A
    git commit -m "JARVIS v0.1.1 — initial baseline" --allow-empty
    git tag baseline

    # Configure GitHub remote if GITHUB_REPO is set
    if [ -n "$GITHUB_REPO" ] && echo "$GITHUB_REPO" | grep -qv "REPLACE"; then
        git remote add origin "$GITHUB_REPO" 2>/dev/null || git remote set-url origin "$GITHUB_REPO"
        echo "[entrypoint] GitHub remote configured: $GITHUB_REPO"
    fi

    echo "$IMAGE_HASH" > /data/code/.image_hash
    echo "[entrypoint] Baseline commit created in /data/code/backend/"
    touch "$HEALTH_FLAG"
else
    echo "[entrypoint] Found existing code backup"

    # ── 2b. Detect image update — merge new files from image into backup ──
    if [ "$IMAGE_HASH" != "$STORED_HASH" ]; then
        echo "[entrypoint] IMAGE UPDATE DETECTED — merging new image files into backup"

        # Merge new/updated files from image into backup, but preserve JARVIS's modifications
        # Strategy: rsync with --ignore-existing for safety, then force-update known new files
        rsync -a --ignore-existing /app/ "$CODE_BACKUP/backend/" --exclude='.git' --exclude='__pycache__' 2>/dev/null || \
            cp -an /app/. "$CODE_BACKUP/backend/" 2>/dev/null || true
        rsync -a --ignore-existing /frontend/ "$CODE_BACKUP/frontend/" --exclude='node_modules' --exclude='.git' 2>/dev/null || \
            cp -an /frontend/. "$CODE_BACKUP/frontend/" 2>/dev/null || true

        # Force-update frontend config (allowedHosts for ngrok)
        cp -f /frontend/vite.config.ts "$CODE_BACKUP/frontend/vite.config.ts" 2>/dev/null || true

        # Force-update critical infrastructure files that the image updated
        # (these are "ours" — from the developer, not JARVIS's modifications)
        for f in \
            jarvis/tools/registry.py \
            jarvis/tools/coding_agent.py \
            jarvis/tools/self_modify.py \
            jarvis/tools/resource_manager.py \
            jarvis/agents/__init__.py \
            jarvis/agents/coding.py \
            jarvis/tools/coding_agent.py \
            jarvis/safety/prompt_builder.py \
            jarvis/core/loop.py \
            jarvis/core/planner.py \
            jarvis/core/executor.py \
            jarvis/core/state.py \
            jarvis/core/email_listener.py \
            jarvis/tools/send_email.py \
            jarvis/tools/skills.py \
            jarvis/tools/http_request.py \
            jarvis/tools/env_manager.py \
            jarvis/api/routes.py \
            jarvis/api/schemas.py \
            jarvis/llm/router.py \
            jarvis/llm/providers/grok.py \
            jarvis/tools/coingecko.py \
            jarvis/tools/self_analysis.py \
            jarvis/budget/tracker.py \
            jarvis/memory/working.py \
            jarvis/memory/vector.py \
            jarvis/memory/blob.py \
            jarvis/models.py \
            jarvis/main.py \
            jarvis/config.py; do
            if [ -f "/app/$f" ]; then
                mkdir -p "$(dirname "$CODE_BACKUP/backend/$f")"
                cp -f "/app/$f" "$CODE_BACKUP/backend/$f"
            fi
        done

        # Commit the image update in the backup repo
        cd "$CODE_BACKUP/backend"
        git add -A
        git commit -m "Image update — merged new files from JARVIS image (hash: ${IMAGE_HASH:0:8})" --allow-empty 2>/dev/null || true

        echo "$IMAGE_HASH" > /data/code/.image_hash
        echo "[entrypoint] Image update merged and committed"
    fi

    # ── 3. Check if last boot crashed (revert flag) ───────────────────────
    if [ -f "$REVERT_FLAG" ]; then
        echo "[entrypoint] REVERT FLAG detected — last boot crashed after code change"
        cd "$CODE_BACKUP/backend"
        LAST_GOOD=$(git log --format='%H' --all | head -2 | tail -1)
        if [ -n "$LAST_GOOD" ]; then
            echo "[entrypoint] Reverting to last known good commit: $LAST_GOOD"
            git reset --hard "$LAST_GOOD"
            echo "[entrypoint] Revert complete"
        fi
        rm -f "$REVERT_FLAG"
    fi

    # Restore code from backup to live locations
    echo "[entrypoint] Syncing /data/code/backend/ -> /app/"
    rsync -a --delete "$CODE_BACKUP/backend/" /app/ --exclude='.git' --exclude='__pycache__' 2>/dev/null || \
        cp -a "$CODE_BACKUP/backend/." /app/

    # Preserve image's vite.config.ts (for allowedHosts/ngrok) before restore overwrites it
    cp -f /frontend/vite.config.ts /tmp/vite.config.ts.bak 2>/dev/null || true

    echo "[entrypoint] Syncing /data/code/frontend/ -> /frontend/"
    rsync -a --delete "$CODE_BACKUP/frontend/" /frontend/ --exclude='node_modules' --exclude='.git' 2>/dev/null || \
        cp -a "$CODE_BACKUP/frontend/." /frontend/

    # Restore image's vite.config.ts so ngrok/allowedHosts works
    if [ -f /tmp/vite.config.ts.bak ]; then
      cp -f /tmp/vite.config.ts.bak /frontend/vite.config.ts
      cp -f /tmp/vite.config.ts.bak "$CODE_BACKUP/frontend/vite.config.ts"
    fi
fi

# Also init git in /app if not already (for self_modify tool)
if [ ! -d "/app/.git" ]; then
    cd /app
    git init
    git add -A
    git commit -m "JARVIS live code — synced from backup" --allow-empty 2>/dev/null || true
fi

# Ensure GitHub remote is always configured in both repos
_ensure_remote "$CODE_BACKUP/backend"
_ensure_remote "/app"
echo "[entrypoint] Git remotes configured"

# ── 4. Syntax check — validate Python code loads ──────────────────────────
echo "[entrypoint] Validating Python code..."
cd /app
if python -c "import jarvis.main" 2>/tmp/import_check.log; then
    echo "[entrypoint] Code validation PASSED"
    rm -f "$REVERT_FLAG"
else
    echo "[entrypoint] CODE VALIDATION FAILED — reverting to last good commit"
    cat /tmp/import_check.log

    cd "$CODE_BACKUP/backend"
    LAST_GOOD=$(git log --format='%H' -1 HEAD~1 2>/dev/null)
    if [ -n "$LAST_GOOD" ]; then
        git reset --hard "$LAST_GOOD"
        cp -a "$CODE_BACKUP/backend/." /app/
        echo "[entrypoint] Reverted to $LAST_GOOD"
    else
        echo "[entrypoint] No previous commit to revert to — using image code"
    fi
    rm -f "$REVERT_FLAG"
fi

# ── 5. Set the revert flag — cleared only after healthy startup ───────────
# If we crash before clearing it, next boot will revert
touch "$REVERT_FLAG"

# ── 6. Start frontend (background) ────────────────────────────────────────
echo "[entrypoint] Starting frontend..."
cd /frontend
npx vite --host 0.0.0.0 --port 3000 &
FRONTEND_PID=$!

# ── 7. Start backend ──────────────────────────────────────────────────────
echo "[entrypoint] Starting backend..."
cd /app

# Background health check: after 30s of healthy running, clear revert flag
(
    sleep 30
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        rm -f "$REVERT_FLAG"
        echo "[health] Backend healthy — cleared revert flag"

        # Sync live code back to backup (in case startup migrations added files)
        # CRITICAL: exclude .git to preserve the persistent repo's history
        rsync -a --exclude='.git' --exclude='__pycache__' /app/ "$CODE_BACKUP/backend/" 2>/dev/null || \
            find /app -maxdepth 1 -not -name '.git' -not -name '.' -exec cp -a {} "$CODE_BACKUP/backend/" \; 2>/dev/null || true
    else
        echo "[health] Backend NOT healthy after 30s — revert flag stays"
    fi
) &

# --workers 1 required for SIGHUP graceful restart (self_modify redeploy)
exec python -m uvicorn jarvis.main:app --host 0.0.0.0 --port 8000 --log-level info --workers 1
