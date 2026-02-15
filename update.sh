#!/bin/bash
set -e

echo "=== Updating JARVIS Docker image ==="

# Create container from existing image
CONTAINER_ID=$(docker create -it jarvis:latest /bin/bash)
echo "Container: $CONTAINER_ID"
docker start $CONTAINER_ID

# Install rsync if not present (needed for code sync)
docker exec $CONTAINER_ID bash -c 'which rsync || apt-get update && apt-get install -y --no-install-recommends rsync' 2>&1 || true

# Copy updated backend code
echo "Copying backend..."
docker cp backend/. $CONTAINER_ID:/app/

# Copy updated frontend code
echo "Copying frontend..."
docker cp frontend/. $CONTAINER_ID:/frontend/

# Copy entrypoint
echo "Copying entrypoint..."
docker cp entrypoint.sh $CONTAINER_ID:/entrypoint.sh
docker exec $CONTAINER_ID chmod +x /entrypoint.sh

# Install any new frontend deps
echo "Installing frontend deps..."
docker exec -w /frontend $CONTAINER_ID npm install 2>&1 || true

# Commit the updated image with new entrypoint
docker commit \
  --change 'WORKDIR /app' \
  --change 'EXPOSE 8000 3000' \
  --change 'CMD ["/bin/bash", "/entrypoint.sh"]' \
  $CONTAINER_ID jarvis:latest

# Cleanup
docker rm -f $CONTAINER_ID

echo "=== JARVIS image updated successfully ==="
echo "Run with: docker compose up"
