# Design

## Context

Ver `proposal.md` — Why y `specs/catalogo-configuracion/spec.md` para el contrato completo. Estado actual relevante:

- `Tenant` (`app/domain/tenant.py`) ya existe con `politicas` (`JSON` con variante `JSONB` en PostgreSQL) y el seed lo inicializa con `{"anticipacion_min_dias": 1, "sena_default_pct": 30, "cancelacion_horas": 24}`.
- `app/domain/rbac.py` ya define `Recurso.CONFIGURACION` con permisos `CRUD` para `dueno` y `SOLO_LECTURA` (`Accion.LEER`) para `recepcion` y `odontologo`.
- `BaseRepository[T]` (`app/infrastructure/db/repository.py`) filtra toda consulta y escritura por `tenant_id` y levanta `TenantContextoRequerido` si falta.
- La última migración en `src/backend/alembic/versions/` es `002_sesiones_tokens_publicos.py` (`revision = "002_sesiones_tokens"`), por lo que la migración de C-04 debe ser `003_catalogo_configuracion.py` con `down_revision = "002_sesiones_tokens"`.

## Goals / Non-Goals

**Goals:**
- Proveer las entidades `Sillon`, `Prestacion` y `CoberturaOS` con constraints a nivel de base de datos y de schema Pydantic (`extra='forbid'`, R1), asegurando que ninguna regla de negocio dependa solo del cliente.
- Exponer el CRUD administrativo bajo `/api/admin/*` con baja lógica (`activo = False` / `activa = False`, R7) y trazabilidad en `auditoria` para cada alta, modificación o baja.
- Soportar consulta de coberturas vigentes a una fecha dada (`vigente_en`) para que C-06 (agenda), C-10 (presupuestos) y C-13 (liquidación OS) puedan resolver el arancel y copago aplicables sin duplicar lógica.
- Extender `ejecutar_seed` de forma 100% idempotente con el sillón `"Box 1"` y las 5 prestaciones base.

**Non-Goals:**
- Cálculo de saldo en turnos o liquidación de obras sociales (corresponde a C-06, C-10, C-11 y C-13).
- UI de administración de catálogo (corresponde a C-17 `frontend-caja-os-admin`).
- Horarios particulares por profesional o bloqueos de agenda (corresponde a C-06 `agenda-turnos`).

## Decisions

### D1 — Constraints en doble capa (Pydantic + SQL `CHECK` / `UNIQUE`)

Las reglas estructurales del catálogo se validan en los schemas de entrada con mensajes rioplatenses (422) **y** se refuerzan en la base de datos mediante `UniqueConstraint` y `CheckConstraint` en la migración `003`:
- `sillon`: `UniqueConstraint("tenant_id", "sucursal", "nombre", name="uq_sillon_tenant_sucursal_nombre")`.
- `prestacion`: `UniqueConstraint("tenant_id", "nombre", name="uq_prestacion_tenant_nombre")`, `CheckConstraint("duracion_min > 0", name="ck_prestacion_duracion_positiva")`, `CheckConstraint("precio_particular >= 0", name="ck_prestacion_precio_no_negativo")` y `CheckConstraint("(NOT requiere_sena) OR (monto_sena IS NOT NULL AND monto_sena > 0)", name="ck_prestacion_sena_valida")`.
- `cobertura_os`: `CheckConstraint("arancel >= 0 AND copago >= 0", name="ck_cobertura_montos_no_negativos")` y `CheckConstraint("vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde", name="ck_cobertura_vigencia_ordenada")`.

**Alternativa considerada:** validar solo en Pydantic — descartada porque cualquier inserción interna o script podría violar las invariantes de seña/duración que exige la agenda.

### D2 — Tipos numéricos exactos (`Numeric(12, 2)`) para importes monetarios

`precio_particular`, `monto_sena`, `arancel` y `copago` se almacenan como `Numeric(12, 2)` en SQLAlchemy/Postgres y se exponen como `Decimal` (o número serializado sin pérdida) en Pydantic, evitando errores de punto flotante en cálculos futuros de señas y liquidaciones (R8).

### D3 — Baja lógica uniforme en `DELETE`

Dado que turnos históricos, presupuestos y liquidaciones referenciarán sillones, prestaciones y coberturas (R7), los endpoints `DELETE /api/admin/{sillones,prestaciones,coberturas}/{id}` no ejecutan `DELETE` físico sino que marcan `activo = False` / `activa = False`, registran la acción en `auditoria` y devuelven el recurso actualizado (o 200 con el estado desactivado). Los listados `GET` devuelven todos los ítems del tenant y aceptan `?solo_activos=true` cuando el consumidor solo quiere los habilitados.

### D4 — Esquema de políticas del tenant compatible hacia atrás

`Tenant.politicas` ya usa las claves `anticipacion_min_dias`, `sena_default_pct` y `cancelacion_horas` en `POLITICAS_SEED` (`app/infrastructure/seed.py`). `PATCH /api/admin/tenant/politicas` valida un schema `PoliticasUpdate(_Estricto)` con esos campos opcionales (más alias o soporte para `anticipacion_min_hs` si se informa, normalizando sobre el diccionario JSONB del tenant), hace merge sobre las políticas existentes del consultorio del token y audita `tenant.actualizar_politicas` con `antes` y `despues`.

### D5 — Verificación de pertenencia de `prestacion_id` al crear/editar `CoberturaOS`

Una `Fk` simple a `prestacion.id` en SQL no impide por sí sola referenciar una prestación de otro `tenant_id`. Antes de insertar o actualizar una `CoberturaOS`, el caso de uso consulta la prestación mediante `BaseRepository(session, actor.tenant_id, Prestacion).obtener(datos.prestacion_id)`; si no existe en el tenant del token, responde `404 NoEncontrado` sin revelar si existe en otro consultorio.

## Risks / Trade-offs

- **[Colisión de numeración de migración con CHANGES.md]** → `CHANGES.md` mencionaba "Migración 002" para C-04 porque se redactó antes de que C-03 ocupara `002_sesiones_tokens`. La secuencia real de Alembic exige `003_catalogo_configuracion` con `down_revision = "002_sesiones_tokens"`; se documenta en `CHANGES.md` y `README.md`.
- **[Diferencias entre SQLite (fallback) y PostgreSQL en `Numeric` y `JSONB`]** → se usa `Numeric(12, 2)` estándar y `JSON().with_variant(JSONB(), "postgresql")`, y los `GRANT`/`REVOKE` a `turnos_app` se ejecutan condicionados a `_es_postgres()` igual que en `001` y `002`.

## Migration Plan

1. Aplicar `003_catalogo_configuracion` (`alembic upgrade head`): crea `sillon`, `prestacion` y `cobertura_os` con sus índices, constraints y `GRANT SELECT, INSERT, UPDATE, DELETE` a `turnos_app`.
2. Ejecutar `python -m app.infrastructure.seed`: agrega `"Box 1"` y las 5 prestaciones base al tenant piloto si no existen.
3. Rollback: `alembic downgrade -1` revoca los permisos de `turnos_app` y elimina `cobertura_os`, `prestacion` y `sillon` en orden inverso de dependencias.
