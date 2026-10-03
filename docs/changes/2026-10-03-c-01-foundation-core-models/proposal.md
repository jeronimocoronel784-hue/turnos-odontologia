# Proposal

## Why

Sin cimiento no avanza ningún change del roadmap: todos (C-03 en adelante) dependen de la app FastAPI, la DB versionada y el aislamiento por `tenant_id`. Se fusionan C-01 y C-02 en un solo ciclo porque la infraestructura sin modelos no verifica nada y los modelos sin infraestructura no corren; juntos entregan un backend despegable con persistencia real desde el día uno.

## What Changes

**Foundation (C-01):**

- Estructura `backend/app/{domain,application,infrastructure,api,workers,tests}` y `frontend/src/{features,shared,pages}` según `08_arquitectura_propuesta.md`.
- FastAPI mínima con `GET /api/health`, SQLAlchemy 2.0 async + Alembic inicializado, `shared/` con settings Pydantic v2, logger, session por request y exceptions con mensajes en rioplatense (RN-GL-02).
- Frontend Vite + React + TS + PWA base (manifest + service worker), React Router, TanStack Query, Tailwind.
- `docker-compose.yml`: api + postgres 15 + redis 7 + worker (+ mailhog dev).
- `.env.example` con las 11 variables de §08; secretos solo `${VAR}`, jamás hardcodeados (RN-SE-04).
- CI GitHub Actions con jobs paralelos backend (pytest) y frontend (tsc + build).

**Modelos core multi-tenant (C-02):**

- Modelos `Tenant` (con `politicas` jsonb), `Usuario` (rol dueno/recepcion/odontologo, email único por tenant, matrícula obligatoria si odontólogo), `Auditoria` (solo INSERT+SELECT, retención 5 años).
- `TenantMixin` (`tenant_id` FK en toda tabla de negocio), `AuditMixin` (`created_at/updated_at`), `BaseRepository[T]` + `UnitOfWork`.
- Migración 001: tablas `tenant`, `usuario`, `auditoria` + índices (`slug`, (`tenant_id`,`email`)).
- Seed mínimo: 1 tenant piloto + 1 usuario Dueño + matriz de permisos base (datos ficticios, R13).
- Tests contra DB real en contenedor: aislamiento multi-tenant, constraint email/tenant, auditoría rechaza UPDATE/DELETE.

## Capabilities

### New Capabilities

- `foundation-setup`: scaffolding del monorepo, FastAPI mínima con health check, frontend PWA base, docker-compose y CI.
- `core-models-multitenant`: entidades raíz multi-tenant (Tenant, Usuario, Auditoria), mixins, repositorio base + UnitOfWork, migración 001 y seed piloto.

### Modified Capabilities

- Ninguna (primer change del proyecto; `openspec/specs/` está vacío).

## Impact

- Crea `backend/`, `frontend/`, `docker-compose.yml`, `.env.example`, `.github/workflows/` (repo hoy solo tiene KB, discovery y docs).
- Desbloquea C-03 (auth/RBAC) y todo el roadmap; es el GATE 0 + GATE 1 en un ciclo.
- Sin breaking changes (no hay consumidores previos).
