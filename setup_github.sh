#!/bin/bash
# ─── JARVIS GitHub Setup Helper ───────────────────────────────────────────
# This script helps you set up GitHub integration for JARVIS.
#
# What you need:
#   1. A GitHub account (JARVIS uses jarvis.bot.g.d@gmail.com)
#   2. A Personal Access Token (PAT) with 'repo' scope
#   3. A GitHub repository (public or private)
# ───────────────────────────────────────────────────────────────────────────
set -e

echo "=== JARVIS GitHub Setup ==="
echo ""
echo "This script will configure GitHub integration so JARVIS can push"
echo "its own code changes to a remote repository."
echo ""

# ── Step 1: Check for existing values ──────────────────────────────────────
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env file not found. Are you in the JARVIS project root?"
    exit 1
fi

CURRENT_TOKEN=$(grep "^GITHUB_TOKEN=" "$ENV_FILE" | cut -d= -f2)
CURRENT_REPO=$(grep "^GITHUB_REPO=" "$ENV_FILE" | cut -d= -f2)

# ── Step 2: Get PAT ───────────────────────────────────────────────────────
echo "─── Step 1: GitHub Personal Access Token (PAT) ───"
echo ""
echo "You need a PAT with 'repo' scope. To create one:"
echo "  1. Go to: https://github.com/settings/tokens?type=beta"
echo "     Or classic: https://github.com/settings/tokens/new"
echo "  2. Give it a name like 'JARVIS'"
echo "  3. Select scope: 'repo' (full control of private repositories)"
echo "  4. Generate and copy the token"
echo ""

if [ -n "$CURRENT_TOKEN" ] && ! echo "$CURRENT_TOKEN" | grep -q "REPLACE"; then
    echo "Current token: ${CURRENT_TOKEN:0:10}... (already set)"
    read -p "Replace it? (y/N): " REPLACE_TOKEN
    if [ "$REPLACE_TOKEN" != "y" ] && [ "$REPLACE_TOKEN" != "Y" ]; then
        TOKEN="$CURRENT_TOKEN"
    fi
fi

if [ -z "$TOKEN" ]; then
    read -p "Paste your GitHub PAT: " TOKEN
    if [ -z "$TOKEN" ]; then
        echo "No token provided. Exiting."
        exit 1
    fi
fi

# ── Step 3: Get repo URL ──────────────────────────────────────────────────
echo ""
echo "─── Step 2: GitHub Repository ───"
echo ""
echo "You need a GitHub repository for JARVIS. Create one at:"
echo "  https://github.com/new"
echo ""
echo "Name it something like 'jarvis' or 'jarvis-brain'."
echo "It can be public or private."
echo ""

if [ -n "$CURRENT_REPO" ] && ! echo "$CURRENT_REPO" | grep -q "REPLACE"; then
    echo "Current repo: $CURRENT_REPO"
    read -p "Replace it? (y/N): " REPLACE_REPO
    if [ "$REPLACE_REPO" != "y" ] && [ "$REPLACE_REPO" != "Y" ]; then
        REPO="$CURRENT_REPO"
    fi
fi

if [ -z "$REPO" ]; then
    read -p "Repository URL (e.g. https://github.com/username/jarvis.git): " REPO
    if [ -z "$REPO" ]; then
        echo "No repo provided. Exiting."
        exit 1
    fi
    # Ensure .git suffix
    if ! echo "$REPO" | grep -q "\.git$"; then
        REPO="${REPO}.git"
    fi
fi

# ── Step 4: Update .env ───────────────────────────────────────────────────
echo ""
echo "─── Step 3: Updating .env ───"

# Replace or add GITHUB_TOKEN
if grep -q "^GITHUB_TOKEN=" "$ENV_FILE"; then
    sed -i.bak "s|^GITHUB_TOKEN=.*|GITHUB_TOKEN=$TOKEN|" "$ENV_FILE"
else
    echo "GITHUB_TOKEN=$TOKEN" >> "$ENV_FILE"
fi

# Replace or add GITHUB_REPO
if grep -q "^GITHUB_REPO=" "$ENV_FILE"; then
    sed -i.bak "s|^GITHUB_REPO=.*|GITHUB_REPO=$REPO|" "$ENV_FILE"
else
    echo "GITHUB_REPO=$REPO" >> "$ENV_FILE"
fi

rm -f "$ENV_FILE.bak"

echo "Updated .env:"
echo "  GITHUB_TOKEN=${TOKEN:0:10}..."
echo "  GITHUB_REPO=$REPO"

# ── Step 5: Test connection ────────────────────────────────────────────────
echo ""
echo "─── Step 4: Testing connection ───"

# Extract username from token
API_RESULT=$(curl -sf -H "Authorization: token $TOKEN" https://api.github.com/user 2>/dev/null || echo '{"login":"unknown"}')
GH_USER=$(echo "$API_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('login','check failed'))" 2>/dev/null || echo "check failed")

if [ "$GH_USER" = "check failed" ] || [ "$GH_USER" = "unknown" ]; then
    echo "WARNING: Could not verify token. Make sure it's valid."
    echo "You can test manually: curl -H 'Authorization: token YOUR_TOKEN' https://api.github.com/user"
else
    echo "Authenticated as: $GH_USER"
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Rebuild or update the Docker image:"
echo "     ./update.sh  (fast, if image exists)"
echo "     ./build.sh   (full rebuild)"
echo ""
echo "  2. Start JARVIS:"
echo "     docker compose up"
echo ""
echo "  3. JARVIS can now push code changes with:"
echo "     self_modify action=push"
echo ""
echo "  Or JARVIS can do it automatically as part of self-improvement."
