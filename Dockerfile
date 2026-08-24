# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ARG VERSION=0.8.0
ARG REVISION=unknown
ARG CREATED=unknown

LABEL org.opencontainers.image.title="Voice Studio" \
      org.opencontainers.image.description="Local multi-provider AI voice studio and OpenAI-compatible gateway" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$REVISION" \
      org.opencontainers.image.created="$CREATED" \
      org.opencontainers.image.source="https://github.com/RainyHorizon/voice-studio"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    VOICE_STUDIO_ROOT=/app \
    VOICE_STUDIO_PORT=8765 \
    VOICE_STUDIO_CREDENTIALS_MODE=env

WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --gid voice --shell /usr/sbin/nologin voice \
    && mkdir -p /app/data/audio \
    && chown -R voice:voice /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /app/backend/requirements.txt
COPY backend/app /app/backend/app
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY LICENSE README.md /app/

RUN chown -R voice:voice /app
USER voice
EXPOSE 8765
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/summary', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
