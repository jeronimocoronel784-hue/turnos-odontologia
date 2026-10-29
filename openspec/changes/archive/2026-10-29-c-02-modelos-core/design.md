# Design

## Context

Ver `proposal.md` (Why) para la motivación. Estado verificado en disco: los modelos core existen bajo el layout viejo (`src/app/domain/`: `tenant.py`, `usuario.py`, `auditoria.py`, `mixins.py`; `src/app/infrastructure/db/`: `repository.py`, `unit_of_work.py`; `src/app/infrastructure/seed.py`; migración `src/alembic/versions/001_initial_tenant_usuario_auditoria.py`; tests en `tests/` con `conftest.py` apuntando a `src/`). Hallazgo central del análisis previo (governance CRITICO: análisis primero): el SQL de GRANTs YA existe en la migración 001 (líneas 90-93: CRUD en tenant/usuario, solo SELECT+INSERT en auditoria para `APP_DB_ROLE`, salteado fuera de Postgres) y el rol lo crea `db/init/01-roles.sh`; los tests de rechazo UPDATE/DELETE YA existen en `tests/test_auditoria_appendonly.py` pero se skipean sin Docker (`APP_ROLE_URL_TEST` + `dialecto == postgresql`). La task 2.4 pendiente es, por tanto, verificación en entorno real — no escritura de SQL nuevo. Constraints: archive `2026-10-03-c-01-foundation-core-models` inmutable (solo lectura), sin moves de directorios (scope de `c-01-solo-setup`, aún no aplicado → verificación post-move bloqueada por c-01), R1/R2/R4/R7/R9/R11/R13.

## Goals / Non-Goals

**Goals:**

- Cerrar 2.4 con evidencia: los 2 casos de rechazo (UPDATE, DELETE) corriendo en verde contra Postgres real con rol app restringido, sin skips en CI/Docker.
- Dejar verificada la paridad funcional de modelos core bajo el nuevo layout en cuanto c-01 se aplique (suite, migración reversible, seed idempotente, aislamiento A/B).
- Regla de governance operativa para 2.4: si la verificación revela GRANTs insuficientes, el SQL correctivo se propone y espera revisión humana antes de escribirse; nunca se commitea SQL de permisos sin review.

**Non-Goals:**

- No se reescriben modelos, mixins, repositorio, UoW, migración 001 ni seed salvo que la verificación pruebe deficiencia (y entonces solo lo mínimo, con review previo por ser CRITICO).
- No se agregan endpoints, RLS, ni servicio frontend; no se toca CI ni compose (eso es c-01: tasks 1.4/4.2/4.3).
- No se elimina el fallback SQLite local ni la política de skip fuera de Postgres (decisión documentada en `conftest.py` + test de auditoría).

## Decisions

### D1. Verificar antes que reescribir (2.4 es cierre, no construcción)

**Qué:** el apply corre primero la suite de auditoría contra Postgres+Doker y solo si un caso falla se diagnostica si el defecto está en el GRANT (migración 001), en el rol (`01-roles.sh`), en el wiring de env (`APP_ROLE_URL_TEST`) o en el test mismo.
**Por qué:** el análisis previo muestra las tres piezas ya implementadas; reescribir SQL de permisos sin evidencia violaría governance CRITICO y arriesga romper lo que ya funciona en CI.
**Alternativa considerada:** reescribir los GRANTs "por las dudas" — descartada (cambio ciego en dominio CRITICO sin test que lo pida).

### D2. Entorno de verdad para 2.4: Postgres en contenedor, nunca SQLite

**Qué:** los casos UPDATE/DELETE se validan con `DATABASE_URL_TEST` apuntando a Postgres migrado + `APP_ROLE_URL_TEST` apuntando a la misma DB con credenciales del rol `turnos_app`. Ojo documentado: `conftest.session` usa `create_all` (sin GRANTs), por eso los tests abren sesión propia restringida vía `_sesion_rol_app()` — la DB bajo test DEBE estar migrada con 001 (no solo `create_all`) para que los GRANTs existan.
**Por qué:** el permiso es un objeto de la DB, no del ORM; solo existe donde corrió la migración como owner.
**Alternativa:** replicar GRANTs en `create_all` de tests — descartada (duplica la fuente de verdad; la migración es la única dueña del DDL de permisos). Compact rules aplicadas (`supabase-postgres-best-practices`): multi-tenant con tests de visibilidad, migraciones reversibles, verificación post-carga.

### D3. Orden de verificación: aislamiento y constraints primero, permisos después

**Qué:** tasks en secuencia — (1) modelos/constraints/aislamiento A/B contra Postgres, (2) migración 001 reversible en contenedor fresco, (3) seed idempotente con doble ejecución, (4) casos 2.4 con rol restringido, (5) gates `ruff`+`mypy`+`extra='forbid'`+grep PHI.
**Por qué:** si el aislamiento base falla, los casos de permiso no significan nada; el orden aísla la causa. Compact rules aplicadas (`tdd`, `python-fastapi-development`): ≥2 casos por comportamiento, schemas Pydantic separados del ORM, async end-to-end; (`hipaa-compliance` como base Ley 25.326: nada de PHI en logs ni errores visibles, auditoría append-only).

### D4. Gate explícito por c-01: verificación post-move bloqueada hasta el move

**Qué:** cada task de paridad post-move lleva precondición "c-01 aplicado" (`src/backend/app/` existe). Si al momento del apply c-01 sigue abierto, esas tasks se reportan bloqueadas — no se "verifican" contra el layout viejo ni se adelantan paths nuevos a mano.
**Por qué:** verificar paridad contra el layout viejo daría falso verde y duplica el trabajo cuando c-01 mueva los archivos.
**Alternativa:** hacer el move dentro de este change — descartada (scope explícito de c-01, proposal de c-01 lo prohíbe en sentido inverso).

### D5. Sin SQL nuevo sin review: protocolo CRITICO para GRANTs

**Qué:** si D1 detecta deficiencia en permisos, el ejecutor presenta el diff SQL propuesto + impacto (qué rol, qué tabla, qué privilegio, por qué el actual es insuficiente) y espera aprobación humana antes de tocar `001_*` (o una migración nueva) y `db/init/`. El test que lo demuestra se escribe primero (TDD estricto, R11 contra DB real).
**Por qué:** permisos de auditoría son append-only legal (retención 5 años, RN-SE-01); un GRANT de más destruye la garantía silenciosamente.
**Alternativa:** auto-aprobar cambios "mínimos" de permisos — descartada por governance CRITICO.

## Risks / Trade-offs

- [Risk] `APP_ROLE_URL_TEST` mal cableada en Docker/CI (apunta a owner en vez de `turnos_app`) → los casos pasarían en falso o fallarían con error confuso → Mitigación: task que verifica el rol efectivo (`SELECT current_user`) antes de los casos de rechazo.
- [Risk] `create_all` vs migración divergen (GRANTs solo en migración) → Mitigación: D2 exige DB migrada para 2.4; task de reversibilidad 001 corre en contenedor fresco separado.
- [Risk] c-01 cambia `conftest.py` (`sys.path` a `src/backend`) y este change lo verifica contra el viejo → Mitigación: D4, gate explícito por c-01.
- [Risk] SQLite local enmascara regresiones Postgres (JSONB vs JSON, CHAR(32), constraints) → Mitigación: el cierre exige corrida contra Postgres real; el verde local solo vale como señal parcial (R11).
- [Trade-off] Se aceptan skips documentados fuera de Postgres a cambio de no bloquear el desarrollo sin Docker; el cierre real ocurre en CI/Docker → queda explícito en specs y tasks.

## Migration Plan

1. Sin cambios de schema previstos (001 ya contiene tablas + GRANTs). Si D1/MyD5 exigen corrección de permisos: nueva migración (no edición de 001 ya aplicada en entornos) + review humano previo.
2. Rollback: revert del commit del change; permisos previos se restauran con `downgrade`/`upgrade` de la migración involucrada en contenedor de prueba antes de tocar shared.
3. Sin datos reales en juego (R13: fixtures sintéticos siempre); sin backfill.

## Open Questions

- Ninguna que cambie specs, enfoque o tasks. Las PO del KB (retención legal exacta, hosting, pricing) siguen abiertas para changes futuros.
