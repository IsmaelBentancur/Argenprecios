# Argenprecios — Dockerfile
# Multi-stage: instala dependencias pesadas (Playwright + Chromium) en una sola capa cacheable.

# ── Stage 1: dependencias Python ──────────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app

# Dependencias del sistema necesarias para Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    # Chromium runtime deps
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 libatspi2.0-0 libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium de Playwright (un solo browser — ~280 MB)
RUN playwright install chromium --with-deps


# ── Stage 2: imagen final ──────────────────────────────────────────────────────
FROM deps AS final

WORKDIR /app

# Copiar código fuente
COPY . .

# Crear directorio de logs (montable como volumen)
RUN mkdir -p logs

# Usuario no-root por seguridad
RUN groupadd -r argenprecios && useradd -r -g argenprecios -d /app argenprecios \
    && chown -R argenprecios:argenprecios /app
USER argenprecios

# Puerto de la API
EXPOSE 8000

# Variables de entorno con defaults — pueden sobreescribirse con .env o docker-compose
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MONGO_URI=mongodb://mongodb:27017 \
    MONGO_DB=argenprecios \
    API_HOST=0.0.0.0 \
    API_PORT=8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
