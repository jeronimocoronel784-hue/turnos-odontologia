# Proposal

## Why

El ciclo fundacional (archive `2026-10-03-c-01-foundation-core-models`) dejó 4 tasks sin tildar: 1.4, 2.4, 4.2 y 4.3. El change `c-01-solo-setup` absorbe el re-movido de layout más 1.4/4.2/4.3, pero la task 2.4 (rol app restringido a INSERT+SELECT sobre `auditoria`, con UPDATE/DELETE rechazados por la DB) sigue abierta y es governance CRITICO: no puede mezclarse en un change BAJO. Este change cierra ese gap y verifica los modelos core contra el nuevo layout `src/backend/` + `src/frontend/`, cerrando el árbol C-01→C-02 del CHANGES.md original.

## What Changes

- Gap-closure de modelos core contra el nuevo layout (sin moves de directorios — eso es scope de `c-01-solo-setup`):
  - Verificar `Tenant` (slug único, `politicas` jsonb), `Usuario` (unicidad (`tenant_id`,`email`), matrícula obligatoria si odontólogo), `Auditoria` (append-only) + `TenantMixin`/`AuditMixin` bajo `src/backend/`.
  - Verificar `BaseRepository[T]` + `UnitOfWork` con aislamiento A/B (tenant A no ve filas de B; mismo email en otro tenant SÍ permitido).
  - Verificar migración 001 reversible (`upgrade head` + `downgrade -1` + `upgrade` en contenedor fresco) y seed idempotente (doble ejecución sin duplicados, datos 100% sintéticos).
  - Verificar gates R2/R1: `ruff` + `mypy` limpios, `extra='forbid'` en inputs Pydantic, sin PHI en logs (R9).
  - Regression post-move: imports `from app...`, `tests/conftest.py`, `DATABASE_URL_TEST` y suite contra Postgres real (R11).
- CERRAR la pendiente 2.4 (governance CRITICO): rol app con GRANT INSERT+SELECT sobre `auditoria`, UPDATE/DELETE rechazados por permiso insuficiente con ≥2 casos, solo en Postgres (nunca en SQLite). Análisis primero según governance: proponer el SQL de GRANTs y esperar revisión humana antes de escribirlo.
- Si `c-01-solo-setup` aún no está aplicado al diseñar/implementar, las tasks de verificación post-move quedan marcadas como bloqueadas por c-01.

## Capabilities

### New Capabilities

- Ninguna (no hay comportamiento nuevo; es cierre y verificación de lo ya especificado).

### Modified Capabilities

- `core-models-multitenant`: precisa el requirement de auditoría append-only (GRANT INSERT+SELECT a nivel de rol DB, alcance solo-Postgres, verificación con ≥2 casos) y agrega el requirement de verificación post-move (modelos, migración 001, seed y aislamiento verdes bajo el layout `src/backend/`, bloqueado por c-01 si el move aún no está aplicado).

## Impact

- Afecta: `src/backend/app/domain/` (tenant, usuario, auditoría, mixins), `src/backend/app/infrastructure/db/` (repository, unit_of_work), `src/backend/alembic/versions/001_*`, seed, `tests/test_core_models.py`, `test_repository_isolation.py`, `test_auditoria_appendonly.py`, `test_seed.py`, `db/init/` (GRANTs).
- **BREAKING**: ninguno para API/contratos (sin endpoints nuevos; cambios solo en permisos DB y verificación).
- Desbloquea: cierre del árbol C-01→C-02 y base verificada para C-03 (`auth-rbac-tokens`, que consume `tenant_id` del token y la matriz RBAC).
- No toca: layout de directorios (c-01), RLS futura (opcional), frontend, CI, secretos (R10: solo `${VAR}`), datos reales (R13: solo fixtures sintéticos).
