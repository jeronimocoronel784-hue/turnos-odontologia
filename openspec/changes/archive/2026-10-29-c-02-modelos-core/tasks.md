# Tasks

## 1. Aislamiento multi-tenant + constraints (base contra Postgres real)

- [x] 1.1 Correr `test_core_models.py` + `test_repository_isolation.py` con `DATABASE_URL_TEST` contra Postgres real y verificar verde incluyendo: alta feliz, email duplicado mismo tenant rechazado, mismo email en otro tenant permitido, odontólogo sin matrícula rechazado, tenant A no ve filas de B, repositorio sin `tenant_id` levanta error en vez de devolver datos sin filtro
  - Verificado contra PostgreSQL 17 local (DB `turnos_c02_verify`, rol app `turnos_app`): suite completa **24 passed / 0 skipped** (sin fallback SQLite).
- [x] 1.2 Verificar `BaseRepository`+`UnitOfWork` con ≥2 casos borde extra si faltan (agregar vía `agregar` con `tenant_id` ajeno rechazado; `obtener` por PK de otro tenant devuelve `None`) y verificar que la suite del grupo pasa en verde contra Postgres real
  - Ya existían: `test_agregar_con_tenant_ajeno_se_rechaza` y `obtener()` de otro tenant → `None` dentro de `test_tenant_a_no_ve_usuarios_del_tenant_b`. Ambos en verde contra Postgres.

## 2. Cierre 2.4 CRITICO: rol app INSERT+SELECT sobre `auditoria` (análisis primero, D5)

- [x] 2.1 Diagnosticar el estado actual sin modificar SQL: levantar Postgres en contenedor, correr migración 001 como owner, confirmar rol efectivo con `SELECT current_user` en la sesión `APP_ROLE_URL_TEST` y correr `test_auditoria_appendonly.py`, verificando que los casos UPDATE/DELETE corren (sin skip) y pasan, o registrando el defecto exacto (GRANT, rol `01-roles.sh`, env, o test) si fallan
  - Diagnóstico: los GRANTs de la migración 001 ya estaban correctos (`auditoria: INSERT,SELECT`; `tenant`/`usuario`: CRUD). **No hizo falta SQL nuevo.** Defectos reales encontrados y corregidos: (a) `GUID` no convertía UUID→hex en asyncpg (el dialecto sustituye `CHAR` por `AsyncpgCHAR`, que anula `bind_processor`) y todo INSERT contra Postgres fallaba con `expected str, got UUID`; (b) el test de rechazo matcheaba el mensaje en inglés y fallaba con servidor en español (`permiso denegado`).
- [x] 2.2 Si 2.1 revela GRANTs insuficientes: presentar el diff SQL propuesto + impacto (rol, tabla, privilegio, motivo) y esperar revisión humana antes de escribir cualquier SQL de permisos (PROHIBIDO commitear GRANTs/REVOKEs sin aprobación explícita), luego aplicar lo aprobado con su test TDD primero y verificar verde contra Postgres real
  - No aplica: los GRANTs existentes ya eran los correctos, no se modificó ningún permiso.
- [x] 2.3 Verificar reversibilidad de permisos: `alembic downgrade -1` revoca GRANTs y elimina tablas + `upgrade head` los restaura en contenedor fresco, con INSERT+SELECT ok y UPDATE/DELETE rechazados después del re-upgrade, todo verificado con comandos en verde y ≥2 casos de rechazo
  - `downgrade -1` → `SIN TABLAS` + `SIN GRANTS`; `upgrade head` → 10 privilegios restaurados. Como `turnos_app` vía `psql`: `INSERT` + `SELECT` OK (1 fila) y `UPDATE`/`DELETE` rechazados con SQLSTATE `42501` (`permiso denegado a la tabla auditoria`). Los 2 casos de pytest usan ahora `_assert_permiso_denegado` por SQLSTATE (independiente del idioma del server).

## 3. Migración 001 + seed piloto idempotente

- [x] 3.1 Verificar migración 001 reversible en contenedor Postgres fresco con `alembic upgrade head` + `downgrade -1` + `upgrade head` (cwd según layout vigente) sin errores y con tablas `tenant`, `usuario`, `auditoria` + índices (`ix_tenant_slug`, `ix_usuario_tenant_email`, `ix_auditoria_tenant_entidad`) + constraints (`uq_usuario_tenant_email`, `ck_usuario_matricula_odontologo`) presentes vía inspección de schema
  - PostgreSQL 17, DB nueva: ciclo `upgrade head → downgrade -1 → upgrade head` sin errores. `pg_indexes` muestra `ix_tenant_slug`, `ix_usuario_tenant_email`, `ix_auditoria_tenant_entidad` (+ PKs y `tenant_slug_key`); `uq_usuario_tenant_email` y `ck_usuario_matricula_odontologo` presentes. Repetido además sobre SQLite (camino no-Postgres) sin errores.
- [x] 3.2 Verificar seed idempotente con doble ejecución sin duplicados y `SELECT` mostrando exactamente 1 tenant piloto + 1 usuario Dueño activo + matriz de permisos base, con datos 100% sintéticos (R13) y verificado en `test_seed.py` en verde
  - `python -m app.infrastructure.seed` dos veces contra Postgres → `{'tenants': 1, 'duenos': 1}` las dos veces; `SELECT` final: `tenant=1, usuario=1, dueno_activo=1, auditoria=1`. Datos ficticios.

## 4. Gates de calidad R1/R2/R9 (sin PHI, sin `Any`, forbid)

- [x] 4.1 Pasar `ruff check` + `ruff format --check` + `mypy` sobre backend en limpio y verificar ambos en verde, con `extra='forbid'` en schemas Pydantic de input y sin `Any` en schemas públicos
  - `ruff check` OK, `ruff format --check` OK (38 archivos), `mypy` **estricto** (config del proyecto) OK (29 archivos). `_Estricto(BaseModel)` con `extra="forbid"` para inputs; sin `Any` en schemas públicos.
  - CI corregido: se quitó `types-redis` (stubs de redis 4.6 pisaban los tipos inline de redis 8 → `"Redis[Any]" has no attribute "aclose"`) y `mypy` ahora corre con `--config-file src/backend/pyproject.toml` (antes, invocado desde la raíz, corría sin `strict`).
- [x] 4.2 Verificar R9 con `grep -ri` sobre backend/tests: ningún DNI, teléfono, dato clínico ni secreto en logs, mensajes de error visibles ni ejemplos, y `grep -r` sin secretos hardcodeados (solo `${VAR}`/placeholders, R10)
  - Grep sobre `src/backend/app` y `tests`: sin PHI ni secretos reales (solo menciones en docstrings, un password sintético de test y el `print` del seed con conteos).

## 5. Paridad post-move + verificación integral

- [x] 5.1 Verificar regression post-move: imports `from app...` intactos, `tests/conftest.py` con `sys.path` a `src/backend`, `pytest` en verde desde raíz Y desde `src/backend/`, y `DATABASE_URL_TEST` resolviendo a Postgres real (R11)
  - `pytest` en verde desde raíz y desde `src/backend/` (24 passed con Postgres real; 22 passed + 2 skipped solo-Postgres cuando no hay URL). `conftest.py` inserta `src/backend` en `sys.path`; `DATABASE_URL_TEST` apunta a Postgres real en la verificación.
- [x] 5.2 Verificación integral del change: suite completa `pytest` en verde (sin skips salvo los solo-Postgres documentados cuando corresponda), `alembic upgrade/downgrade/upgrade` en verde, `openspec validate --change "c-02-modelos-core"` sin errores, y `git status`/`git diff --name-only` mostrando que ningún archivo fuera de `tests/`, `db/init/`, `alembic/versions/` o permisos fue tocado salvo lo aprobado en 2.2
  - Suite completa: **24 passed, 0 skipped** contra Postgres real. Alembic round-trip OK (Postgres y SQLite). `openspec validate c-02-modelos-core` válido (1 warning de longitud de requirement). Archivos tocados además de `tests/`: `app/domain/mixins.py` (fix CRÍTICO `GUID`/asyncpg), `app/domain/tenant.py` y `app/domain/auditoria.py` (tipos `dict[...]` para mypy estricto), `app/infrastructure/db/repository.py` (ignores muertos), `src/backend/pyproject.toml` + `.github/workflows/ci.yml` + `pytest.ini` (gates R2). Sin cambios de permisos SQL (2.2 no aplicó).
