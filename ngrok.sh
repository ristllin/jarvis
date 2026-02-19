#!/bin/bash
# Run ngrok to expose the JARVIS dashboard.
# Requires: docker compose up (with nginx on port 80), ngrok installed locally.
# Usage: ./ngrok.sh   or   source .env && ngrok start --config ngrok.yml web

set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if [ -z "$NGROK_AUTHTOKEN" ]; then
  echo "Error: NGROK_AUTHTOKEN not set. Add it to .env"
  exit 1
fi

export NGROK_AUTHTOKEN

POLICY_FILE="$(dirname "$0")/ngrok-policy.yml"
DOMAIN="collins-saxicolous-moveably.ngrok-free.dev"

if [ -f "$POLICY_FILE" ]; then
  exec ngrok http 80 --domain="$DOMAIN" --traffic-policy-file="$POLICY_FILE"
else
  echo "Warning: ngrok-policy.yml not found. Run without Basic Auth."
  exec ngrok http 80 --domain="$DOMAIN"
fi
