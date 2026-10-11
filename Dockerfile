# Multi-stage Dockerfile for VESTA Full-Stack Web Deployment
# Stage 1: Build React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# Stage 2: Python Backend Runtime
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt uvicorn fastapi duckdb

# Copy project files
COPY . .
COPY --from=frontend-builder /app/web/dist ./web/dist

# Configure environment
ENV VESTA_DATA_TIER=hot
ENV PYTHONUNBUFFERED=1
ENV PORT=8899

EXPOSE 8899

# Startup: Auto-download Hot Tier DuckDB from Cloudflare R2 if missing, then start FastAPI
CMD ["bash", "-c", "if [ ! -f db/hot/vesta_ohlcv.duckdb ]; then echo 'Fetching Hot DB from Cloudflare R2...'; mkdir -p db/hot && curl -sSL https://pub-42c10f4f37494be4bbb1ed357bde3dcd.r2.dev/vesta_hot_tier.zip -o db/hot/vesta_hot_tier.zip && unzip -q db/hot/vesta_hot_tier.zip -d db/hot/ && rm -f db/hot/vesta_hot_tier.zip; fi; python -m uvicorn src.service.console_api:app --host 0.0.0.0 --port ${PORT:-8899}"]
