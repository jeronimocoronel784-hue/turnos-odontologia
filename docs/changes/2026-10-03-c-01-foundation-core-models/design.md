# Design

## Context

Ver `proposal.md` (Why) para la motivación. Estado actual: repo greenfield sin `backend/` ni `frontend/`; solo KB, discovery y docs. Constraints que moldean el diseño: multi-tenant lógico desde el día 1 (`tenant_id` en todo, KB §04/§08), reglas duras R1-R4 y R7 de AGENTS.md, TDD estricto con DB real en contenedor (R11), y los skill standards (multi-stage-dockerfile, python-fastapi-development, supabase-postgres-best-practices, tdd).

## Goals / Non-Goals

**Goals:**

- Stack local `docker compose up` funcional: api + postgres 15 + redis 7 + worker + mailhog.
- Persistencia async real (SQLAlchemy 2.0 + Alembic) con migración 001 reversible y seed piloto ficticio.
- Aislamiento por tenant verificable por tests desde el primer change.
- Frontend PWA base que muestra el estado de la API y deja el esqueleto `features/shared/pages` listo.

**Non-Goals:**

- Auth/RBAC (C-03), catálogos, pacientes y agenda: solo se dejan los ganchos (`tenant_id`, `BaseRepository`, `UnitOfWork`), no sus endpoints.
- RLS de Postgres: se pospone a futuro; v1 aísla por filtro en repositorio + tests (decisión explícita abajo).
- Deploy cloud/VPS y TLS productivo: este change es local-first (PO-01 sigue abierta).

## Decisions

### D1. Monolito modular FastAPI con separación domain/application/infrastructure

**Qué:** `backend/app/{domain,application,infrastructure,api,workers,tests}` según KB §08; routers por dominio en `api/`, casos de uso en `application/`, reglas RN en `domain/`.
**Por qué:** un equipo chico despliega una sola API; la separación impide que reglas de negocio filtren a routers y deja C-03..C-17 como agregados, no refactors.
**Alternativa considerada:** microservicios por dominio — descartado por costo operativo sin volumen que lo justifique (KB §02 lo declara suposición explícita).

### D2. SQLAlchemy 2.0 async + session por request, schemas Pydantic separados

**Qué:** engine async, `AsyncSession` por request vía dependencia FastAPI; modelos ORM NUNCA expuestos — schemas request/response explícitos con `extra='forbid'` (R1); type hints + `ruff` + `mypy` limpios (R2); errores custom con handlers globales y mensajes rioplatenses (RN-GL-02), sin stack traces al cliente.
**Por qué:** R1-R3 son reglas duras; el async end-to-end evita bloquear el event loop cuando entren WA/MP (C-08, C-12).
**Alternativa:** sync + `Session` clásica — descartada por R3.

### D3. Aislamiento multi-tenant por filtro en `BaseRepository` + `tenant_id` del JWT, sin RLS en v1

**Qué:** `TenantMixin` agrega `tenant_id` FK a toda tabla de negocio; `BaseRepository[T]` inyecta el filtro automáticamente desde el contexto (que en C-03 vendrá del JWT, R4); `UnitOfWork` agrupa la transacción.
**Por qué:** RLS agrega complejidad operativa (roles por tenant, migraciones con downtime) sin beneficio para el piloto de 1 tenant; el filtro + tests de aislamiento (tenant A no ve B) dan la garantía exigible hoy y el camino a RLS queda abierto (columna ya existe).
**Alternativa:** RLS desde día 1 — descartada por costo/beneficio en piloto; se reevalúa si un audit lo exige.

### D4. Auditoría append-only enforced en DB, no solo en código

**Qué:** rol de DB de la app con GRANT solo INSERT+SELECT sobre `auditoria` (+ REVOKE UPDATE/DELETE); retención 5 años por prudencia (supuesto KB §04, PO-03 abierta para confirmación legal); soft delete como única baja lógica en entidades futuras (R7).
**Por qué:** RN-SE-01/RN-GL-03 no admiten atajos: si la inmutabilidad vive solo en Python, un bug la rompe en silencio; el permiso DB la hace estructural.
**Alternativa:** trigger `BEFORE UPDATE/DELETE ... RAISE` — válido como refuerzo, queda como mejora opcional si el GRANT por rol complica Alembic/seed.

### D5. Migración 001 mínima + seed idempotente con datos ficticios

**Qué:** Alembic 001 crea `tenant`, `usuario`, `auditoria` + índices (`slug`, (`tenant_id`,`email`), (`tenant_id`,`entidad`,`entidad_id`,`created_at`)); seed con tenant piloto + Dueño ficticio + permisos base, re-ejecutable sin duplicar (upsert por slug/email).
**Por qué:** el seed es el fixture del piloto y de CI; R13 exige datos sintéticos siempre y la idempotencia evita estados divergentes entre dev/CI.
**Alternativa:** seed solo en SQL suelto — descartado porque Alembic versiona el esquema y el seed vive en código testeable.

### D6. Docker multi-stage + CI paralela

**Qué:** builder separado de runtime, base oficial con tag exacto, `.dockerignore`, USER no-root, HEALTHCHECK, sin secretos en la imagen (skill multi-stage-dockerfile); `docker-compose.yml` con api/postgres/redis/worker/mailhog; GitHub Actions con jobs paralelos backend/frontend.
**Por qué:** imagen final mínima y sin secretos (RN-SE-04); CI paralela acorta el feedback y cada job verifica su capa (pytest vs `tsc`+build).
**Alternativa:** un solo job CI secuencial — descartado por tiempo de feedback.

### D7. Frontend PWA mínimo pero con las decisiones caras ya tomadas

**Qué:** Vite + React + TS estricto (sin `any`, R5), Router, TanStack Query como cliente API único, Tailwind, manifest + service worker base, estructura `features/shared/pages`; NUNCA datos clínicos en `localStorage` (R6, deja el precedente aunque este change no maneja clínica).
**Por qué:** Router + Query + estructura de features son caros de retrofittear; el SW base deja el camino a la cola offline de C-15.

## Risks / Trade-offs

- [Risk] Filtro por tenant olvidado en una query futura expone datos cruzados → Mitigación: `BaseRepository` centraliza el filtro, tests de aislamiento obligatorios por change (mínimo 2 casos), y `tenant_id` del JWT (R4) elimina la fuente más común del error.
- [Risk] Permisos GRANT sobre `auditoria` rompen migraciones/seed si Alembic usa el mismo rol → Mitigación: rol owner para DDL/seed, rol app restringido solo en runtime; test explícito de rechazo UPDATE/DELETE con el rol app.
- [Risk] Async + SQLAlchemy 2.0 tiene curva de aprendizaje (greenlet, eager loading) → Mitigación: patrones fijados en este change (session por request, `selectinload` por defecto) que el resto copia; `mypy`+`ruff` atrapan el resto.
- [Risk] Fusionar C-01+C-02 agranda el change (~1 sesión larga de 6h) → Mitigación: tasks.md ordena foundation primero con gates verificables; si se atrasa, se puede archivar foundation sola y mover modelos (los specs ya separan las capabilities).
- [Trade-off] Sin RLS: la garantía es por código + tests, no por motor → aceptado para piloto, documentado y reversible.

## Migration Plan

1. `docker compose up --build` levanta stack limpio.
2. `alembic upgrade head` aplica 001 (reversible: `downgrade -1` elimina las 3 tablas; solo válido pre-datos reales).
3. Seed idempotente crea tenant + Dueño + permisos.
4. Rollback: `docker compose down -v` vuelve a cero (dev); en CI cada run parte de contenedores frescos. Sin datos reales en juego, no hay plan de backfill.

## Open Questions

- Ninguna que cambie specs, enfoque o tasks. Quedan las PO abiertas del KB (hosting PO-01, retención legal PO-03, pricing PO-04) que afectan a changes futuros, no a este.
