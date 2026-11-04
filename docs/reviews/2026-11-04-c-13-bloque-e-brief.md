# Brief de implementación — C-13 Bloque E (reglas comunes para los agentes)

> Leer antes de implementar. Fuente de verdad del alcance: `docs/reviews/2026-11-04-c-13-fix-plan.md`
> + `openspec/changes/c-13-obras-sociales-liquidacion/tasks.md` (bloque `## 6. Bloque E`).

## Reglas duras del proyecto (`AGENTS.md`)

- **R1** nunca exponer modelos SQLAlchemy crudos → schemas Pydantic (`extra='forbid'` en inputs).
- **R2** type hints obligatorios; `ruff` + `mypy` limpios en los archivos del change.
- **R3** async end-to-end; nunca I/O sync bloqueando el loop.
- **R4** el `tenant_id` del token JWT manda; nunca confiar en el `tenant_id` del body/query.
- **R7** nunca hard delete en HC/turnos/caja → soft delete + auditoría append-only.
- **R8** nunca montos calculados en el cliente; totales SIEMPRE desde el detalle persistido.
- **R9** nunca PHI (DNI, teléfono, datos clínicos) en logs, errores, URLs ni textos libres.
- **R11** tests contra DB real (Postgres), sin mocks de DB; mínimo 2 casos por comportamiento.
- **R13** nunca datos reales de pacientes: fixtures sintéticos.

## TDD estricto (obligatorio)

Por cada tarea: **RED** (test que falla) → **GREEN** (código mínimo) → **TRIANGULATE** (≥2 casos por
comportamiento: happy path + borde) → **REFACTOR** (tests en verde tras cada paso) → marcar la tarea.
Nada de aserciones tautológicas ni tests que no ejerciten comportamiento.
En el resumen final incluí la tabla de evidencia TDD (tarea → archivo de test → RED/GREEN/TRIANGULATE/REFACTOR).

## Entorno de tests

- **SQLite (loop de desarrollo, fallback por defecto)**: `python -m pytest -q` desde la raíz.
  Baseline actual: **508 passed, 1 failed (preexistente de C-04: `tests/test_catalogo_documentacion.py::test_rutas_catalogo_existen_en_la_app`), 4 skipped**.
- **Postgres 17 real (R11)**: instancia desechable local en `127.0.0.1:5433` (NO tocar el Postgres del
  usuario en 5432):
  ```powershell
  $env:DATABASE_URL_TEST  = "postgresql+asyncpg://postgres@127.0.0.1:5433/turnos_c13_verify"
  $env:APP_ROLE_URL_TEST  = "postgresql+asyncpg://turnos_app:turnos_app_verify@127.0.0.1:5433/turnos_c13_verify"
  python -m pytest -q tests/test_liquidaciones_estados.py tests/test_liquidaciones_negocio.py `
    tests/test_liquidaciones_unicidad.py tests/test_liquidaciones_api.py tests/test_liquidaciones_export.py `
    tests/test_schemas_liquidaciones.py -p no:cacheprovider
  ```
  La DB está migrada a head (001..012) con los GRANTs del rol app.

### Regla CRÍTICA de orden de INSERTs (Postgres)

El ORM del proyecto **no declara `relationship()`** → SQLAlchemy no ordena los INSERTs y Postgres
(que sí aplica las FK) rechaza el hijo si se inserta antes del padre. En los seeds de tests:
**siempre `await session.flush()` entre el `add_all` de los padres y el de los hijos.**
`tests/test_liquidaciones_export.py` (líneas ~109-136) y `tests/test_liquidaciones_api.py` (~93-120) hoy
mezclan padres e hijos en un mismo flush: hay que partirlo en dos flushes.

## Lint y tipos

```powershell
python -m ruff check --config src/backend/pyproject.toml src/backend tests
python -m ruff format --check --config src/backend/pyproject.toml src/backend tests
python -m mypy --config-file src/backend/pyproject.toml src/backend/app src/backend/alembic
```
Baseline: `ruff check` → 13 errores preexistentes, todos en `tests/` (imports sin usar de C-11/C-12) y
**ninguno** en los archivos de C-13; `ruff format --check` → 3 archivos; `mypy` → **Success (106 archivos)**.
No dejes errores nuevos: si tocás un archivo, que quede limpio.

## OpenSpec

```powershell
openspec validate c-13-obras-sociales-liquidacion --strict
```

## Reglas de trabajo

- NO hagas `git commit` ni `git push` (el orquestador commitea).
- NO modifiques: `src/backend/alembic/versions/012_obras_sociales_liquidacion.py` (ya aplicada en bases
  reales → los cambios de esquema van en la migración correctiva `013`), `knowledge-base/*`, `README.md`,
  `CHANGES.md` (los documente otro agente).
- No rompas los tests existentes: si un test codifica el comportamiento defectuoso (p. ej.
  `test_tras_pagar_el_alta_avisa_que_es_complementaria`), **reescribilo** y explicá por qué en el resumen.
