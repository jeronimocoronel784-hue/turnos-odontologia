# Spec Delta

## MODIFIED Requirements

### Requirement: Auditoría append-only con retención de 5 años

La tabla `auditoria` SHALL aceptar solo INSERT y SELECT para el rol app (`APP_DB_ROLE`, default `turnos_app`); cualquier intento de UPDATE o DELETE con ese rol SHALL ser rechazado por la base de datos con error de permiso insuficiente, y el registro queda intacto. El enforcement vive en la migración 001 (GRANT SELECT, INSERT + REVOKE del resto, con downgrade que revierte los permisos); los registros SHALL conservarse un mínimo de 5 años. El enforcement por permiso solo rige en PostgreSQL: en otros dialectos (SQLite local) el DDL de roles se saltea y los casos de rechazo se skipean, corriendo siempre en CI con Postgres real.

#### Scenario: UPDATE sobre auditoría rechazado (borde)

- **Dado** un registro existente en `auditoria` y una sesión con el rol app restringido en PostgreSQL
- **Cuando** se intenta modificarlo con UPDATE
- **Entonces** la base de datos rechaza la operación por permiso insuficiente y el registro queda intacto

#### Scenario: DELETE sobre auditoría rechazado (borde)

- **Dado** un registro existente en `auditoria` y una sesión con el rol app restringido en PostgreSQL
- **Cuando** se intenta eliminarlo con DELETE
- **Entonces** la base de datos rechaza la operación por permiso insuficiente y el registro queda intacto

#### Scenario: INSERT y SELECT con rol app permitidos

- **Dado** una sesión con el rol app restringido en PostgreSQL
- **Cuando** registra un evento de auditoría y luego lo lee
- **Entonces** ambas operaciones tienen éxito y el evento queda persistido con actor, acción, entidad, valores antes/después y timestamp

#### Scenario: Cambio crítico deja rastro auditable

- **Dado** un usuario del tenant A autenticado
- **Cuando** crea o modifica un usuario del tenant A
- **Entonces** queda un registro en `auditoria` con actor, acción, entidad, valores antes/después y timestamp

#### Scenario: Casos de rechazo se skipean fuera de Postgres

- **Dado** un entorno sin PostgreSQL con rol app restringido (SQLite local sin `APP_ROLE_URL_TEST`)
- **Cuando** corre la suite de auditoría
- **Entonces** los casos de rechazo UPDATE/DELETE se skipean con mensaje que indica la verificación pendiente, y el resto de la suite corre normal

## ADDED Requirements

### Requirement: Paridad funcional de modelos core bajo el layout `src/backend/`

El sistema SHALL mantener el comportamiento completo de modelos core (Tenant, Usuario, Auditoría, mixins, `BaseRepository`+`UnitOfWork`, migración 001 reversible, seed idempotente) tras el re-movido de layout del change `c-01-solo-setup`: la suite existente SHALL pasar en verde con imports `from app...` intactos, `tests/conftest.py` apuntando a `src/backend/` y `DATABASE_URL_TEST` contra Postgres real (R11). Si `c-01-solo-setup` aún no está aplicado, esta verificación SHALL considerarse bloqueada por c-01 y no se da por cumplida en el layout viejo.

#### Scenario: Suite core en verde post-move

- **Dado** el layout `src/backend/` + `src/frontend/` ya aplicado por c-01
- **Cuando** corre `pytest` desde la raíz contra Postgres real
- **Entonces** los tests de modelos, aislamiento multi-tenant, auditoría, seed y settings pasan en verde sin skips salvo los documentados solo-Postgres

#### Scenario: Migración 001 reversible desde el nuevo cwd

- **Dado** el layout `src/backend/` ya aplicado por c-01 y un contenedor Postgres fresco
- **Cuando** se ejecuta `alembic upgrade head`, luego `downgrade -1`, luego `upgrade head` con cwd en `src/backend/`
- **Entonces** las tres operaciones terminan sin errores y las tablas `tenant`, `usuario` y `auditoria` quedan creadas con sus índices y constraints

#### Scenario: Verificación bloqueada si c-01 no está aplicado

- **Dado** que `c-01-solo-setup` aún no está aplicado (layout plano-mezclado en `src/`)
- **Cuando** se evalúa este requirement
- **Entonces** se reporta como bloqueado por c-01 y no se marca cumplido, sin reescribir paths del layout viejo
