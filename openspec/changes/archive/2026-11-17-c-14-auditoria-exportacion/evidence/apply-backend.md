# Evidencia de apply backend — C-14 auditoria-exportacion

## Baseline

- Suite backend: 579 passed, 2 failed (env: test_settings, test_comunicaciones_api), 8 skipped.
- No se tocaron los 2 fallos de entorno ni Postgres.

## Batch 1

Tareas: 1.1–1.4 (trail `GET /api/auditoria`) y 2.1 (RBAC matrix extension).

### RED

- `pytest tests/test_auditoria_consulta.py` → 16 failed (endpoint inexistente).
- `pytest tests/test_rbac_matriz.py` → (pre-cambio) fallaba al agregar `EXPORTACION_TENANT`/`PACIENTES.EXPORTAR` sin implementar.

### GREEN

- Implementado `listar_auditoria(...)` en `app/application/auditoria.py` (filtros combinados, orden `created_at DESC, id DESC`, keyset `(created_at, id)`, cursor base64url, normalización ART→UTC, validaciones `EntidadInvalida`).
- Creado `app/api/routers/auditoria.py` con `GET /api/auditoria` protegido con `requiere(Recurso.AUDITORIA, Accion.LEER)`, registrado en `app/main.py` y en `conftest.py`.
- Extendido `app/domain/rbac.py`: `Recurso.EXPORTACION_TENANT` (solo Dueño, `EXPORTAR`) y `PACIENTES` con `EXPORTAR` solo Dueño; fila `Recurso.EXPORTACION` (C-13) intacta.
- `pytest tests/test_schemas_auditoria.py` → 8 passed.
- `pytest tests/test_auditoria_consulta.py` → 12 passed (trail), 4 failed por alcance posterior (exportación/paquete, fuera de este batch).
- `pytest tests/test_rbac_matriz.py` → 8 passed.
- `pytest tests/test_auditoria_documentacion.py` → 3 passed.

### Archivos creados/modificados

- `src/backend/app/application/auditoria.py`
- `src/backend/app/api/routers/auditoria.py`
- `src/backend/app/api/schemas_auditoria.py` (ya existente, sin cambios)
- `src/backend/app/domain/rbac.py`
- `src/backend/app/main.py`
- `tests/conftest.py`
- `tests/test_rbac_matriz.py`
- `tests/test_auditoria_documentacion.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`

## Batch 2

Tareas: 2.2 (matriz 3 roles sobre `/api/auditoria`) y 2.3 (aislamiento multi-tenant) y 2.5 parcial (tres caminos × tres roles, xfail en datasets/paquete).

### RED (antes)

- `pytest tests/test_auditoria_consulta.py` → 12 passed, 4 failed (`test_tres_caminos_por_tres_roles` ×3 y `test_periodo_por_defecto...`, endpoints de exportación/paquete inexistentes).

### GREEN (después)

- 2.2: matriz de 3 roles verificada (Dueño 200, Recepción 403, Odontólogo 403) con mensaje rioplatense `PermisoInsuficiente` y sin datos en los rechazos.
- 2.3: aislamiento multi-tenant verificado (trail solo tenant A; `?tenant_id=<B>` no amplía alcance, R4). `pytest ... -k tenant` → 1 passed.
- 2.5: trail disponible en `test_tres_caminos_por_tres_roles` (3 roles); datasets (4 × CSV/JSON) y paquete del paciente en `test_tres_caminos_por_tres_roles_datasets_y_paquete` marcados `pytest.mark.xfail(reason="endpoint pendiente (tarea 4.x/6.x)", strict=True)`. `pytest -k "roles or matriz"` → 17 passed, 3 xfailed.
- `pytest tests/test_auditoria_consulta.py` → 15 passed, 4 xfailed.

### Archivos creados/modificados

- `tests/test_auditoria_consulta.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`

## Batch 3

Tareas: 3.1 (HTTP 405 + evento sigue existiendo) y 3.2 (matriz `borrar` denegado para los 3 roles + sin rutas de escritura en OpenAPI). 3.3 queda bloqueada (Docker apagado).

### RED (antes)

- `/api/auditoria/{id}` devolvía `404` para `DELETE`/`PUT`/`PATCH` (sin ruta registrada para el path param).
- `pytest tests/test_auditoria_appendonly.py` → 1 passed, 2 skipped (sin casos de API).

### GREEN (después)

- Registrado `GET /api/auditoria/{evento_id}` (placeholder que lanza `NoEncontrado`) en `app/api/routers/auditoria.py`, de modo que FastAPI devuelve `405` por método no permitido para `DELETE`/`PUT`/`PATCH` sobre `/api/auditoria` y `/api/auditoria/{id}` (autenticado o no).
- `borrar` sobre `Recurso.AUDITORIA` ya estaba denegado para los 3 roles (fila `SOLO_LECTURA`/`NINGUNO`); ratificado por test de matriz.
- OpenAPI no declara rutas de escritura bajo `/api/auditoria`.
- `pytest tests/test_auditoria_appendonly.py` → 4 passed, 2 skipped (los 2 de DB siguen skipeados por falta de Docker, sin tocarlos).
- `pytest tests/test_auditoria_appendonly.py tests/test_rbac_matriz.py` → verde.

### Archivos creados/modificados

- `src/backend/app/api/routers/auditoria.py`
- `tests/test_auditoria_appendonly.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`


## Batch 4

Tareas: 4.1 (test RED) y 4.2 (implementacion `app/shared/sanitizar_phi.py`).

### RED (antes)

- `pytest tests/test_sanitizar_phi.py` -> fallaba por `ModuleNotFoundError: No module named 'app.shared.sanitizar_phi'`.

### GREEN (despues)

- Implementado `src/backend/app/shared/sanitizar_phi.py` con funcion pura `sanitizar_phi` (y aliases) que reutiliza `PATRON_DNI`/`PATRON_TELEFONO` de `app/domain/textos_libres.py` y extiende para DNI con puntos, CUIT/CUIL con guiones y telefonos con separadores; exporta `DATO_OCULTO = "[dato oculto]"` (con aliases de constante).
- `pytest tests/test_sanitizar_phi.py` -> 16 passed.

### Archivos creados/modificados

- `tests/test_sanitizar_phi.py`
- `src/backend/app/shared/sanitizar_phi.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`

## Batch 5

Tareas: 4.3, 4.4 y 4.5 (exportación directa de datasets).

### RED (antes)

- `pytest tests/test_exportacion_datasets.py` → no existía el archivo; endpoint inexistente.

### GREEN (después)

- Creado `tests/test_exportacion_datasets.py` (12 tests): cabeceras exactas de los 4 datasets, CSV/JSON, enmascarado en caja/liquidaciones, dataset vacío, 422 para dataset/formato inválidos, RBAC (Recepción 403), aislamiento de tenant, pacientes ignora rango, JSON con `Decimal` como string, `Content-Disposition`/`Cache-Control: no-store`, nombre de archivo sin PHI.
- Creado `app/api/schemas_exportacion.py` con `ExportacionJobRead`, `DatasetExportable`, `FormatoExportacion` (y `ExportacionDatasetRead`).
- Creado `app/application/exportacion.py` con columnas cerradas de D4, cálculo del período ART en servidor, enmascarado, CSV UTF-8 con BOM/CRLF, JSON con `Decimal` como string, nombre `exportacion-<dataset>-<período>-<opaco>.<ext>`, `EXPORTACION_UMBRAL_FILAS` (default 5000) y `contar_filas_dataset`/`exportar_dataset`.
- Creado `app/api/routers/exportacion.py` con `GET /api/exportacion/{dataset}`, guard `requiere(Recurso.EXPORTACION_TENANT, Accion.EXPORTAR)`, patrón de C-13 y conteo previo contra el umbral (borde `<=`); registrado en `app/main.py` y `conftest.py`.
- `pytest tests/test_exportacion_datasets.py` → 12 passed.

### Archivos creados/modificados

- `tests/test_exportacion_datasets.py`
- `src/backend/app/api/schemas_exportacion.py`
- `src/backend/app/application/exportacion.py`
- `src/backend/app/api/routers/exportacion.py`
- `src/backend/app/main.py`
- `tests/conftest.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`

## Batch 6

Tareas: 4.6 (validacion de rango), 4.7 (auditoria del export directo) y 4.8 (tests de documentacion y seguridad).

### RED (antes)
- `pytest tests/test_exportacion_datasets.py -k rango` -> sin casos de rango.
- `pytest tests/test_exportacion_datasets.py -k auditoria` -> sin casos de auditoria.
- `tests/test_exportacion_documentacion.py` y `tests/test_exportacion_seguridad.py` -> inexistentes.

### GREEN (despues)
- Implementada validacion de rango con `SolicitudInvalida` (maximo 366 dias, fechas ISO-8601, `hasta` futuro, `desde <= hasta`, interpretacion ART por defecto) en `_validar_rango` de `app/application/exportacion.py`.
- Insertado evento `exportacion.solicitar` (dataset, formato, filas, modo `directo`, sin PHI ni nombre de archivo) en la misma transaccion del export directo en `app/api/routers/exportacion.py`, con rollback y `500`/`503` si la auditoria falla.
- Agregados parametros OpenAPI (dataset enum, formato enum, fechas) y respuestas documentadas `200/202/400/403/422/503` en el router.
- Creados `tests/test_exportacion_documentacion.py` y `tests/test_exportacion_seguridad.py`.
- `pytest tests/test_exportacion_datasets.py -k rango` -> 4 passed.
- `pytest tests/test_exportacion_datasets.py -k auditoria` -> 3 passed.
- `pytest tests/test_exportacion_documentacion.py tests/test_exportacion_seguridad.py` -> 8 passed.

### Archivos creados/modificados
- `src/backend/app/application/exportacion.py`
- `src/backend/app/api/routers/exportacion.py`
- `tests/test_exportacion_datasets.py`
- `tests/test_exportacion_documentacion.py`
- `tests/test_exportacion_seguridad.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`

## Batch 7

Tareas: 5.1 (tests RED), 5.2 (settings + env example + test sin TTL) y 5.3 (estado del job en Redis + endpoints de consulta/descarga).

### RED (antes)
- `tests/test_exportacion_jobs.py` inexistente.
- Sin `exportaciones_dir`/`exportacion_umbral_filas` en `Settings`; sin variables en `.env.example`.
- Sin endpoints `GET /api/exportacion/jobs/{job_id}` ni `/descarga`.

### GREEN (después)
- Agregado a `app/shared/settings.py` `exportaciones_dir` (default `/var/tmp/turnos-exportaciones`) y `exportacion_umbral_filas` (default 5000), sin variable de TTL (vencimiento fijo 24 h). Sumadas a `.env.example`.
- Test en `tests/test_settings.py` que verifica la ausencia de cualquier variable de TTL en `Settings` y en `.env.example`.
- Implementado en `app/application/exportacion.py`: constantes `EXPORTACIONES_DIR`, `JOB_TTL_SEGUNDOS` (24 h fija), `COLA_JOBS`, `JOB_ESTADOS`, helpers `clave_job`, `leer_job_exportacion`, y `purgar_exportaciones_vencidas()`.
- Modificado `app/api/routers/exportacion.py`: camino asíncrono cuando `filas > umbral` — job en Redis (hash `exportacion:job:{tenant_id}:{job_id}`, TTL 24 h) en estado `pendiente` + evento `exportacion.solicitar` (modo `asincronico`) antes del commit; `RPUSH` a `turnos:jobs` después; `503` sin job ni evento si Redis falla al crear el job; `503` con evento conservado y job en `error` si falla el `RPUSH`.
- Expostos `GET /api/exportacion/jobs/{job_id}` y `GET /api/exportacion/jobs/{job_id}/descarga` con guard de Dueño (`Recurso.EXPORTACION_TENANT`), `409` si no está `listo` (incluye `error`), `404` uniforme para job de otro tenant, vencido o con archivo borrado.
- `pytest tests/test_exportacion_jobs.py` → 10 passed.
- `pytest tests/test_settings.py` → 4 passed.
- `pytest tests/test_exportacion_datasets.py tests/test_exportacion_documentacion.py tests/test_exportacion_seguridad.py` → 26 passed.

### Archivos creados/modificados
- `src/backend/app/shared/settings.py`
- `src/backend/app/application/exportacion.py`
- `src/backend/app/api/routers/exportacion.py`
- `tests/test_exportacion_jobs.py`
- `tests/test_settings.py`
- `.env.example`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`


## Batch 8

Tareas: 5.4 (worker `exportar_dataset`), 5.5 (purga de archivos vencidos) y 5.6 (evento asíncrono sin duplicado + pedidos repetidos).

### RED (antes)
- `app/workers/main.py` solo procesaba `procesar_outbox`; no existía el tipo `exportar_dataset`.
- `purgar_exportaciones_vencidas()` existía pero el worker no la invocaba ni la throttlaba.
- `tests/test_exportacion_purga.py` inexistente.

### GREEN (después)
- Implementado `exportar_dataset` en `app/workers/main.py`: transición `pendiente → procesando → listo/error`, reutiliza `exportar_dataset` de aplicación, escribe `{job_id}.{ext}` en `EXPORTACIONES_DIR`, borra el archivo parcial en `finally` si falla, sin PHI en logs.
- `run()` barre al arrancar, en cada vuelta del loop con throttle de 300 s y antes de procesar cada job.
- `purgar_exportaciones_vencidas()` borra archivos con antigüedad mayor a 24 h.
- El evento `exportacion.solicitar` modo `asincronico` (con `job_id`) ya se inserta antes de exponer el `job_id`; el worker no lo duplica.
- `tests/test_exportacion_purga.py` creado (purga de 25 h, conserva recientes, worker barre, job vencido 404).
- `tests/test_exportacion_jobs.py` extendido con test del worker (marca `listo` y descarga), test de un único evento de auditoría (worker no duplica) y test de pedidos repetidos (dos eventos, dos jobs).
- `pytest tests/test_exportacion_jobs.py tests/test_exportacion_purga.py` → 17 passed.
- `pytest tests/test_exportacion_jobs.py -k auditoria` → 2 passed.

### Archivos creados/modificados
- `src/backend/app/workers/main.py`
- `tests/test_exportacion_purga.py`
- `tests/test_exportacion_jobs.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`


## Batch 8

Tareas: 5.4 (worker `exportar_dataset`), 5.5 (purga de archivos vencidos) y 5.6 (evento asíncrono sin duplicado + pedidos repetidos).

### RED (antes)
- `app/workers/main.py` solo procesaba `procesar_outbox`; no existía el tipo `exportar_dataset`.
- `purgar_exportaciones_vencidas()` existía pero el worker no la invocaba ni la throttlaba.
- `tests/test_exportacion_purga.py` inexistente.

### GREEN (después)
- Implementado `exportar_dataset` en `app/workers/main.py`: transición `pendiente → procesando → listo/error`, reutiliza `exportar_dataset` de aplicación, escribe `{job_id}.{ext}` en `EXPORTACIONES_DIR`, borra el archivo parcial en `finally` si falla, sin PHI en logs.
- `run()` barre al arrancar, en cada vuelta del loop con throttle de 300 s y antes de procesar cada job.
- `purgar_exportaciones_vencidas()` borra archivos con antigüedad mayor a 24 h.
- El evento `exportacion.solicitar` modo `asincronico` (con `job_id`) ya se inserta antes de exponer el `job_id`; el worker no lo duplica.
- `tests/test_exportacion_purga.py` creado (purga de 25 h, conserva recientes, worker barre, job vencido 404).
- `tests/test_exportacion_jobs.py` extendido con test del worker (marca `listo` y descarga), test de un único evento de auditoría (worker no duplica) y test de pedidos repetidos (dos eventos, dos jobs).
- `pytest tests/test_exportacion_jobs.py tests/test_exportacion_purga.py` → 17 passed.
- `pytest tests/test_exportacion_jobs.py -k auditoria` → 2 passed.

### Archivos creados/modificados
- `src/backend/app/workers/main.py`
- `tests/test_exportacion_purga.py`
- `tests/test_exportacion_jobs.py`
- `openspec/changes/c-14-auditoria-exportacion/tasks.md`
- `openspec/changes/c-14-auditoria-exportacion/evidence/apply-backend.md`

## Batch 9

- 6.1 tests/test_paciente_exportacion.py
- 6.2 app/api/schemas_paciente_exportacion.py
- 6.3 app/application/pacientes.py
- 6.4 app/api/routers/pacientes.py

## Batch 10

Tareas: 9.1, 9.2, 9.3, 9.4 y 10.4 (docs + lint/types + validate).

### 9.1 — Documentación README
- Sección "Auditoría y Exportación (C-14)" agregada a `README.md` (endpoints, permisos solo Dueño, umbral, TTL fijo 24 h, purga, tabla de columnas por dataset, enmascarado de caja/liquidaciones, variables de entorno, operación).
- Verificado contra OpenAPI generado (dataset enum, formato, params de fecha, respuestas 200/202/400/403/422/503).

### 9.2 — Desvío RBAC
- Documentado en README el desvío respecto de `knowledge-base/03_actores_y_roles.md:32,34`, argumento de mínimo necesario y consulta al PO abierta.
- Verificado: sin referencias a TTL configurable ni a `EXPORTACION_TTL_HORAS` en docs, `.env.example` ni settings (`grep` vacío; `tests/test_settings.py` verde).

### 9.3 — Lint y tipos
- `ruff check --config src/backend/pyproject.toml src/backend tests` → All checks passed!
- `ruff format --check ...` → 212 files already formatted (0 to reformat).
- `mypy src/backend/app src/backend/alembic` → Success: no issues found in 120 source files.
- Ajustes de type hints (R2): `pacientes.py` (`_resolver_registrar` → `Any`), `zonas.py` (`ZONA_ART: tzinfo`), `jwt.py` (`# type: ignore[import-untyped]`), `exportacion.py` (purga movida a helper sync + `asyncio.to_thread`), router `exportacion.py` (lectura de archivo vía `asyncio.to_thread`, `# type: ignore[arg-type]` en hset), alias conflictivo eliminado en `schemas_paciente_exportacion.py`.

### 9.4 — Alembic / docker compose
- Sin revisión de Alembic nueva: solo `001..013` en `src/backend/alembic/versions/`; `git status` sin `alembic/versions/*` nuevos.
- `docker compose config` ejecutado con Docker disponible → válido (exit 0, config renderizada).

### 10.4 — OpenSpec
- `openspec validate c-14-auditoria-exportacion --strict` → "Change 'c-14-auditoria-exportacion' is valid".
- `openspec status --change "c-14-auditoria-exportacion" --json` → los cuatro artefactos (proposal, specs, design, tasks) en `done`; `isPlanningComplete: true`; `isComplete: true`.
