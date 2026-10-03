# syntax=docker/dockerfile:1
# API + worker (FastAPI). Builder separado de runtime, no-root, sin secretos en imagen.

FROM python:3.12.7-slim-bookworm AS builder
WORKDIR /srv
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/srv/deps . \
    && pip install --no-cache-dir --prefix=/srv/deps uvicorn asyncpg redis

FROM python:3.12.7-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 appuser
WORKDIR /srv/backend
COPY --from=builder /srv/deps /usr/local
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status in (200, 503) else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
