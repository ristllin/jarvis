FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential rsync gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app /data/blob /data/logs /data/state /data/workspace /data/chroma /data/code

WORKDIR /app

# Backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .

# Frontend
RUN mkdir -p /frontend
COPY frontend/package.json /frontend/
WORKDIR /frontend
RUN npm install
COPY frontend/ .
WORKDIR /app

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000 3000
CMD ["/bin/bash", "/entrypoint.sh"]
