# Proposal

## Why

La agenda de turnos (C-06), los presupuestos (C-10) y la liquidación de obras sociales (C-13) necesitan un catálogo clínico-administrativo contra el cual validar qué sillones (boxes) existen en el consultorio, qué prestaciones se ofrecen (con su duración, precio particular, flag de seña exigible y flag de procedimiento invasivo), qué cobertura ofrece cada obra social según vigencia, y cuáles son las políticas operativas del consultorio (anticipación mínima, seña default y horas de cancelación). Hoy `Tenant` solo tiene `politicas` inicializado por seed sin endpoint de administración, y no existen las entidades `Sillon`, `Prestacion` ni `CoberturaOS`.

## What Changes

- **Modelos del catálogo multi-tenant** (`app/domain/`):
  - `Sillon`: box de atención con `tenant_id`, `nombre`, `sucursal` (default `"central"`), `activo` (soft delete con desactivación, R7), y constraint de unicidad por `(tenant_id, sucursal, nombre)`.
  - `Prestacion`: servicio odontológico con `tenant_id`, `nombre`, `duracion_min > 0`, `precio_particular >= 0`, `requiere_sena` (bool), `monto_sena` (obligatorio y `> 0` cuando `requiere_sena = true`), `invasiva` (bool, default `false` para exigir consentimiento previo en C-09) y `activa` (bool).
  - `CoberturaOS`: convenio por obra social y prestación con `tenant_id`, `obra_social`, `prestacion_id` (FK a `prestacion` del mismo tenant), `arancel >= 0`, `copago >= 0`, `vigencia_desde`, `vigencia_hasta` (nullable o `>= vigencia_desde`) y `activa` (bool), más consulta de cobertura vigente para una fecha dada.
- **Endpoints CRUD administrativos bajo `/api/admin`** protegidos con `requiere(Recurso.CONFIGURACION, ...)`:
  - `/api/admin/sillones` (`GET`, `POST`, `PATCH /:id`, `DELETE /:id` como baja lógica `activo=False`).
  - `/api/admin/prestaciones` (`GET`, `POST`, `PATCH /:id`, `DELETE /:id` como baja lógica `activa=False`).
  - `/api/admin/coberturas` (`GET` con filtro opcional de vigencia/OS/prestación, `POST`, `PATCH /:id`, `DELETE /:id` como baja lógica `activa=False`).
  - `GET /api/admin/tenant/politicas` y `PATCH /api/admin/tenant/politicas` para consultar y actualizar las políticas operativas del consultorio (`anticipacion_min_hs` / `anticipacion_min_dias`, `sena_default_pct`, `cancelacion_hs` / `cancelacion_horas`) con validación estricta y registro en `auditoria`.
- **Migración `003_catalogo_configuracion`**:
  - Crea las tablas `sillon`, `prestacion` y `cobertura_os` con sus constraints (`CHECK`, `UNIQUE`, `FOREIGN KEY`), índices por `tenant_id` y permisos `GRANT SELECT, INSERT, UPDATE, DELETE` al rol `turnos_app` (con `REVOKE` en `downgrade`).
- **Extensión del seed piloto idempotente**:
  - Agrega al consultorio piloto el sillón `"Box 1"` (sucursal `"central"`) y las 5 prestaciones base de la KB (`Limpieza` 30', `Consulta` 20', `Arreglo` 45', `Endodoncia` 60', `Extracción` 45') con precios ficticios y flags `requiere_sena`/`invasiva`.
- **BREAKING**: ninguno. Todas las rutas agregadas son nuevas bajo `/api/admin/*`.

## Capabilities

### New Capabilities
- `catalogo-configuracion`: administración multi-tenant de sillones (boxes), catálogo de prestaciones odontológicas, coberturas de obras sociales por vigencia, políticas operativas del consultorio y seed del catálogo base.

### Modified Capabilities

Ninguna.

## Impact

- **Afecta**: `src/backend/app/domain/` (`sillon.py`, `prestacion.py`, `cobertura_os.py`), `src/backend/app/api/` (`routers/admin_catalogo.py`, `schemas_catalogo.py`), `src/backend/app/infrastructure/seed.py`, `src/backend/alembic/versions/003_catalogo_configuracion.py`, `src/backend/app/main.py`, `README.md` y `tests/`.
- **Dependencias**: usa `ActorAutenticado` y `requiere(Recurso.CONFIGURACION, ...)` ya provistos por C-03 (`auth-rbac-tokens`), y `BaseRepository` + `registrar_auditoria` de C-02/C-03.
- **Desbloquea**: C-06 (`agenda-turnos`), C-10 (`presupuestos-planes`) y C-13 (`obras-sociales-liquidacion`).
