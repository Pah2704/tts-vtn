# ===== Frontend build =====
FROM node:20-alpine AS fe-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
RUN cd frontend && npm run build

# ===== Python base =====
FROM python:3.11-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libespeak-ng1 ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*
# --- Piper binary ---
ARG PIPER_VERSION=2023.11.14-2
RUN curl -fL -o /tmp/piper_linux_x86_64.tar.gz \
      https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz \
  && tar -xzf /tmp/piper_linux_x86_64.tar.gz -C /tmp \
  && mkdir -p /opt/piper \
  && cp -a /tmp/piper/. /opt/piper/ \
  && ln -sf /opt/piper/piper /usr/local/bin/piper \
  && ln -sf /opt/piper/piper_phonemize /usr/local/bin/piper_phonemize \
  && find /opt/piper -maxdepth 1 -type f -name 'lib*.so*' -exec ln -sf {} /usr/local/lib/ \; \
  && ldconfig \
  && /opt/piper/piper --help >/tmp/piper-help.txt \
  && rm -rf /tmp/piper /tmp/piper_linux_x86_64.tar.gz
ENV PIPER_HOME=/opt/piper \
    PIPER_PHONEMIZE_ESPEAK_DATA=/opt/piper/espeak-ng-data \
    LD_LIBRARY_PATH=/opt/piper:/usr/local/lib:${LD_LIBRARY_PATH}
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# ===== API image =====
FROM base AS api
COPY backend ./backend
COPY --from=fe-build /app/frontend/dist ./frontend/dist
RUN mkdir -p backend/outputs
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# Dùng uvicorn chạy FastAPI
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ===== Worker image =====
FROM base AS worker
COPY backend ./backend
RUN mkdir -p backend/outputs
ENV PYTHONUNBUFFERED=1
# Chạy Celery worker
CMD ["celery", "-A", "backend.celery_app.celery", "worker", "--loglevel=info"]
