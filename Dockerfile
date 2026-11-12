# Brandora on Render: one container serving the React UI and the FastAPI API.

FROM node:18-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# espeak-ng is the speech engine pyttsx3 drives on Linux (voice-over).
RUN apt-get update \
 && apt-get install -y --no-install-recommends espeak-ng libespeak1 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=ui /ui/dist frontend/dist
ENV PYTHONUNBUFFERED=1 EMBED_PROVIDER=cloudflare
CMD ["sh", "-c", "uvicorn app:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
