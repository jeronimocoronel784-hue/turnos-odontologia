# Tasks

## 1. Scaffolding backend + infraestructura local

- [x] 1.1 Crear estructura `backend/app/{domain,application,infrastructure,api,workers,tests}` + `pyproject.toml` (Python 3.12, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, Alembic, pytest) y verificar con `python --version` y `pip install -e backend` exitoso
- [x] 1.2 Implementar settings Pydantic v2 con las 11 variables de §08 + `.env.example` con placeholders y verificar que arrancar sin `JWT_SECRET` falla nombrando la variable y que `grep -r` no halla secretos en el repo
- [x] 1.3 Implementar `GET /api/health` (checks postgres+redis, mensajes rioplatenses, sin stack traces) con TDD contra DB real y verificar que `pytest backend/app/tests/test_health.py` pasa con ≥2 casos (sano → 200, DB caída → 503)
- [ ] 1.4 Escribir `docker-compose.yml` (api+postgres15+redis7+worker+mailhog) + Dockerfiles multi-stage (no-root, HEALTHCHECK, `.dockerignore`) y verificar con `docker compose up --build` + `GET /api/health` → 200

## 2. Modelos core multi-tenant + migración 001

- [x] 2.1 Implementar `TenantMixin`, `AuditMixin`, `Tenant` (slug único, `politicas` jsonb), `Usuario` (rol enum, unicidad (`tenant_id`,`email`), matrícula obligatoria si odontólogo) y `Auditoria`, con TDD y verificar que `pytest` cubre alta feliz + email duplicado mismo tenant + matrícula faltante
- [x] 2.2 Implementar `BaseRepository[T]` (filtro `tenant_id` automático desde contexto) + `UnitOfWork` y verificar que el test de aislamiento (tenant A no ve filas de B, caso borde email repetido en otro tenant SÍ permitido) pasa contra Postgres real
- [x] 2.3 Crear migración Alembic 001 (tablas + índices) reversible y verificar con `alembic upgrade head` + `alembic downgrade -1` + `upgrade` en contenedor fresco sin errores
- [ ] 2.4 Restringir rol app a INSERT+SELECT sobre `auditoria` y verificar que el test intenta UPDATE/DELETE y la DB lo rechaza (permiso insuficiente) con ≥2 casos
- [x] 2.5 Pasar `ruff` + `mypy` en limpio sobre `backend/` y verificar con ambos comandos en verde y sin `Any` expuesto en schemas públicos (`extra='forbid'` en inputs)

## 3. Frontend PWA base

- [x] 3.1 Scaffold Vite + React + TS estricto (sin `any`) + Router + TanStack Query + Tailwind con estructura `features/shared/pages` y verificar con `tsc --noEmit` y `vite build` en verde
- [x] 3.2 Agregar manifest PWA + service worker base + página raíz que muestra estado de la API y verificar que el manifest es válido (nombre/iconos) y la página refleja conectado/error ante `GET /api/health`

## 4. Seed piloto + CI + cierre

- [x] 4.1 Implementar seed idempotente (1 tenant + 1 Dueño + permisos base, datos 100% ficticios) y verificar con doble ejecución sin duplicados y `SELECT` que muestra exactamente 1 tenant y 1 dueño
- [ ] 4.2 Agregar workflow CI con jobs paralelos backend (pytest contra Postgres/Redis de servicio) y frontend (`tsc` + build) y verificar con `act` local o push a rama que ambos jobs corren en paralelo y en verde
- [ ] 4.3 Verificación integral del ciclo: `docker compose down -v`, `up --build`, migrar, seedear, `GET /api/health` → 200, suite completa `pytest` en verde, y `openspec validate --change "c-01-foundation-core-models"` sin errores
