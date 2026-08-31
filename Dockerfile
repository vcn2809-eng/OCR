# ==========================================
# Stage 1: Build React Frontend
# ==========================================
FROM node:18-bullseye-slim AS frontend-builder
WORKDIR /build

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Main Application & OCR Engine
# ==========================================
FROM python:3.11-slim-bullseye

ENV PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    PORT=5001 \
    DB_HOST=db \
    DB_PORT=5432 \
    DB_NAME=scanner \
    DB_USER=postgres \
    DB_PASSWORD=postgres

WORKDIR /app

# Install system binaries: Tesseract OCR, Poppler (pdftoppm), OpenCV dependencies, Node.js 18
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js Express server dependencies
COPY server/package*.json ./server/
RUN cd server && npm install --omit=dev

# Copy application source code
COPY app/ ./app/
COPY server/ ./server/
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Copy compiled React frontend from Stage 1
COPY --from=frontend-builder /build/dist ./frontend/dist

# Expose Web & API Port
EXPOSE 5001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5001/api/stats || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
