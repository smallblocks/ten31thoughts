# Ten31 Thoughts - Single Container Dockerfile for StartOS
# Everything runs in one container: FastAPI app + APScheduler + embedded ChromaDB + SQLite
# StartOS constraint: one Dockerfile, no docker-compose

# ─── Stage 1: Build React frontend ───
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: Application ───
FROM python:3.12-slim

# System dependencies (includes WeasyPrint requirements)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    build-essential \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY tools/ ./tools/
COPY docker_entrypoint/ ./docker_entrypoint/
RUN chmod +x ./docker_entrypoint/*.sh

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./static

# Create data directories
RUN mkdir -p /data /data/briefings /data/chromadb

# Download pre-built seed database (historical MacroVoices + Timestamp analysis)
# This gives every install the full historical knowledge base from day one.
# To update: upload a new seed-data.tar.gz to a GitHub Release and rebuild.
ARG SEED_DATA_URL=""
RUN if [ -n "$SEED_DATA_URL" ]; then \
      echo "Downloading seed database from $SEED_DATA_URL..." && \
      curl -fsSL "$SEED_DATA_URL" -o /tmp/seed-data.tar.gz && \
      tar xzf /tmp/seed-data.tar.gz -C /data/ && \
      rm /tmp/seed-data.tar.gz && \
      echo "Seed database installed: $(ls -la /data/ten31thoughts.db 2>/dev/null || echo 'no db') $(du -sh /data/chromadb 2>/dev/null || echo 'no chromadb')" ; \
    else \
      echo "No seed data URL provided — starting with empty database" ; \
    fi

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////data/ten31thoughts.db
ENV CHROMADB_PERSIST_DIR=/data/chromadb

EXPOSE 8431

# Health check for StartOS
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8431/api/health || exit 1

# Single entrypoint — uvicorn runs FastAPI which starts APScheduler internally
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8431", "--workers", "1"]
