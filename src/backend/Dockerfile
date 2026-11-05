# syntax=docker/dockerfile:1
# API + worker (FastAPI). Builder separado de runtime, no-root, sin secretos en imagen.

FROM python:3.12.7-slim-bookworm AS builder
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir --prefix=/srv/deps . \
    && pip install --no-cache-dir --prefix=/srv/deps uvicorn asyncpg redis

FROM python:3.12.7-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 appuser
WORKDIR /srv/src
COPY --from=builder /srv/deps /usr/local
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
USER appuser
EXPOSE 8000
# El chequeo vive en app/healthcheck.py: un `try/except` dentro de `python -c`
# en una sola línea es `SyntaxError`, dejaba el contenedor siempre `unhealthy`
# y EasyPanel nunca reemplazaba el contenedor viejo. Sirve para api y worker.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-m", "app.healthcheck"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
