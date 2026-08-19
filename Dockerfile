# ============================================================
#  Akıllı Restaurant Yönetim Sistemi
#  Çok aşamalı yapı: küçük ve kök olmayan çalışma imajı
# ============================================================

# ---------- 1. aşama: bağımlılıkları derle ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Derleme için gereken paketler (yalnızca bu aşamada)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip install "psycopg[binary]" channels-redis gunicorn

# ---------- 2. aşama: çalışma imajı ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings

# Yalnızca çalışma zamanı bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Kök olmayan kullanıcı — güvenlik gereği
RUN groupadd -r restaurant && useradd -r -g restaurant -m -d /home/restaurant restaurant

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=restaurant:restaurant . .

# Çalışma zamanı klasörleri
RUN mkdir -p /app/logs /app/media /app/staticfiles /app/backups \
    && chown -R restaurant:restaurant /app

USER restaurant

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz/ || exit 1

# WebSocket (mutfak ekranı) için ASGI sunucusu gerekir
CMD ["sh", "-c", "python manage.py migrate --noinput && \
                  python manage.py collectstatic --noinput && \
                  daphne -b 0.0.0.0 -p 8000 config.asgi:application"]
