#!/bin/bash
set -e

echo "=== Building JARVIS Docker image ==="

# Create a container from the base image, install deps, copy code
CONTAINER_ID=$(docker create -it python:3.11-slim /bin/bash)
echo "Container: $CONTAINER_ID"

# Install system deps
docker start $CONTAINER_ID
docker exec $CONTAINER_ID apt-get update
docker exec $CONTAINER_ID apt-get install -y --no-install-recommends git curl build-essential rsync
docker exec $CONTAINER_ID mkdir -p /app /data/blob /data/logs /data/state /data/workspace /data/chroma /data/code

# Copy backend code
docker cp backend/. $CONTAINER_ID:/app/

# Install Python deps
docker exec -w /app $CONTAINER_ID pip install --no-cache-dir -r requirements.txt

# Install Node.js for frontend
docker exec $CONTAINER_ID bash -c 'curl -fsSL https://deb.nodesource.com/setup_20.x | bash -'
docker exec $CONTAINER_ID apt-get install -y nodejs

# Copy frontend and build
docker exec $CONTAINER_ID mkdir -p /frontend
docker cp frontend/. $CONTAINER_ID:/frontend/
docker exec -w /frontend $CONTAINER_ID npm install

# Copy entrypoint
docker cp entrypoint.sh $CONTAINER_ID:/entrypoint.sh
docker exec $CONTAINER_ID chmod +x /entrypoint.sh

# Commit the image
docker commit \
  --change 'WORKDIR /app' \
  --change 'EXPOSE 8000 3000' \
  --change 'CMD ["/bin/bash", "/entrypoint.sh"]' \
  $CONTAINER_ID jarvis:latest

# Cleanup
docker rm -f $CONTAINER_ID

echo "=== JARVIS image built successfully ==="
echo "Run with: docker compose up"
