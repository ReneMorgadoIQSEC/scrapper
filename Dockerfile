FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Montar un volumen de Railway en /data conserva la caché entre despliegues.
    SPECS_CACHE_PATH=/data/specs_cache.json

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

# Un solo proceso: la caché, los límites de peticiones y la deduplicación de scraping viven en memoria.
# "exec" deja a uvicorn recibir el SIGTERM de Railway y guardar la caché antes de apagarse.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
