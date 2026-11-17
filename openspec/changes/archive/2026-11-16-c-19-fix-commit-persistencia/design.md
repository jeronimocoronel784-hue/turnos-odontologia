# Design

## Context

Ver `proposal.md` — Why. El estado actual que condiciona el cómo:

- **Routers sin commit**: `pacientes.py` (flush en las líneas 127, 135, 184, 223, 262), `clinica.py`, `caja.py` y `presupuestos.py` (0 ocurrencias de `session.commit()`) terminan sus endpoints mutantes con `flush()` o delegan en funciones de `app/application/*` que solo flushean. Los otros 9 routers del proyecto (`agenda`, `auth`, `comunicaciones`, `liquidaciones`, `lista_espera`, `reserva_publica`, `admin_catalogo`, `usuarios`, `webhooks_mercadopago`) **sí** commitean al final de cada endpoint mutante (convención dominante: `agenda.py:138` etc.).
- **Cierre de sesión sin commit**: `src/backend/app/api/deps.py:20-24` (`sesion_db`) hace `async with factory() as session: yield session` — solo cierra al terminar la request; SQLAlchemy revierte lo no confirmado. La fábrica (`app/shared/database.py:21`) usa `expire_on_commit=False`, así que los objetos devueltos quedan accesibles tras un `commit()`.
- **Ceguera de la suite**: `tests/conftest.py:198-201` (`_app_de_prueba`) sobreescribe `deps.sesion_db` con `_sesion()` que cede **siempre la misma sesión compartida** del test → los flush se ven en esa sesión; el commit único del fixture ocurre en el teardown (conftest:135) después de los DELETE de limpieza. Ningún test de pacientes/HC/caja/presupuestos abre una sesión nueva para verificar persistencia cross-sesión. Existe un **precedente exacto** del test correcto en `tests/test_liquidaciones_api.py:741-763`: crea un `engine` nuevo con `create_engine_for(db_url)` y verifica la fila desde otra sesión ("el router confirma la transacción: la liquidación existe para otras sesiones").
- **UnitOfWork sin uso**: `app/infrastructure/db/unit_of_work.py` define `UnitOfWork` + `usar_uow` (commit automático al salir del contexto) pero **ningún router lo importa**; es infraestructura huérfana (D1/D3 de C-01).
- **Restricciones**: R3 (async, session por request), R11 (tests contra DB real en contenedor, ≥2 casos por comportamiento), R7/R8/R9/R13 (sin hard delete, montos en servidor, sin PHI, fixtures sintéticas), gobernanza CRÍTICO (persistencia de HC/turnos/caja). Artefactos en es-AR sin PHI.
- **Referencias de dominio "Leer antes"** (coherentes con la entrada C-19 de `CHANGES.md`): `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados (sesión por request / Unit of Work), `knowledge-base/04_modelo_de_datos.md` §Auditoria (append-only, misma transacción) y §Caja/Movimiento (cierre cerrado inmutable), `knowledge-base/05_reglas_de_negocio.md` RN-SE-01, y `AGENTS.md` R3/R7/R8/R11.

## Goals / Non-Goals

**Goals**

- Que toda respuesta `2xx` de un endpoint mutante de los 4 routers corresponda a una escritura confirmada y visible desde otra sesión/request.
- Atomicidad todo-o-nada por operación (entidad + relacionados + auditoría en una transacción).
- Cerrar la ceguera de la suite: tests de persistencia **cross-sesión** que fallen sin el fix y lo detecten en el futuro.
- Fix quirúrgico: sin cambiar contratos, códigos de respuesta, lógica de negocio ni el resto de los routers.

**Non-Goals**

- Reescribir la gestión de sesiones de la app (no se toca `deps.sesion_db` ni `session_por_request`).
- Migrar los 4 routers (o el resto) a `UnitOfWork`/`usar_uow` — consolidación futura posible, fuera de este fix.
- Tocar la capa `application/*`: sigue siendo `flush()` puro; el commit es responsabilidad del endpoint (convención existente).
- Cambios en esquema/migraciones/seeds, en la PWA, en contratos de API ni en los 9 routers que ya commitean.
- Actualizar `CHANGES.md` ni pushear (lo hace el orquestador en tarea aparte).

## Decisions

### D1 — Commit en el endpoint (convención dominante), no en UnitOfWork ni en `deps.sesion_db`

Cada endpoint mutante de los 4 routers termina con `await session.commit()` después de la última escritura (flush + `registrar_auditoria`), antes de construir la respuesta — exactamente el patrón de `agenda.py:138`, `liquidaciones.py:129` y el resto.

- *Por qué*: es la convención ya usada por los 9 routers que persisten correctamente; el cambio es de una línea por endpoint, fácil de revisar en un dominio CRÍTICO; `expire_on_commit=False` en la fábrica hace seguro devolver el ORM ya commiteado.
- *Alternativa descartada — auto-commit en `deps.sesion_db`*: cambiaría el semantics de **todos** los endpoints (incluidos los que ya commitean) con un solo punto de edición, pero rompería el patrón "commit explícito en el endpoint" del repo, haría doble commit donde ya lo hay, y (crítico) quedaría **fuera del alcance de la suite**: `_app_de_prueba` sobreescribe `deps.sesion_db`, así que un fix ahí no lo ejercitaría ningún test actual ni los nuevos cross-sesión. Además el cierre del `async with` en una dependencia yield no distingue éxito/failure de la request sin try/except adicional.
- *Alternativa descartada — envolver cada endpoint con `usar_uow`*: commit automático al salir, pero exige reestructurar los 4 routers (context manager en 28 endpoints), los tests existentes mockean la sesión compartida (el commit automático del UoW la commitearía a mitad de tests que hoy dependen del flush visible), y `UnitOfWork` no tiene hoy ningún uso real en el repo. Riesgo/masa de cambio muy superior para el mismo efecto. Se anota como consolidación futura opcional, no parte de este change.

### D2 — El commit va después de la auditoría y antes de serializar la respuesta

Orden en cada endpoint mutante: escrituras → `flush()` (si hace falta obtener IDs) → `registrar_auditoria(...)` → `await session.commit()` → return/serialización.

- *Por qué*: la auditoría debe quedar en la misma transacción que el hecho (spec: "Auditoría en la misma transacción"); commitear antes de serializar garantiza que si la serialización falla la escritura igualmente no quede colgando sin confirmar en la request que respondió `2xx`... en la práctica FastAPI serializa después del `return`, así que el commit debe ocurrir **dentro** del cuerpo del endpoint, no en un middleware.
- *Endpoints con early-return* (p. ej. `actualizar_paciente` sin cambios, `dar_de_baja_paciente` ya inactivo): no hay escritura que confirmar; se commitea solo en la rama que mutó (o se pone el commit antes del return final de esa rama). No commitear en GET.

### D3 — Tests cross-sesión como guard, con el patrón ya probado en liquidaciones

Nuevo archivo `tests/test_persistencia_commit.py` (o extensión de los archivos `*_api.py` existentes por dominio) con un helper que, después del request `2xx`, abre un **engine y sesión nuevos** con `create_engine_for(db_url)` (mismo `db_url` de la fixture de sesión) y verifica la fila — replicando `tests/test_liquidaciones_api.py:741-763`.

- *Por qué*: es la única forma de que la suite detecte el bug; los tests que usan la sesión compartida pasan con o sin commit.
- *Cobertura mínima (R11: ≥2 casos por comportamiento)*: por cada dominio (pacientes, clínica, caja, presupuestos) al menos: (a) alta `2xx` visible desde sesión nueva, (b) caso borde — operación fallida `4xx` no deja escrituras parciales visibles desde sesión nueva. Se suma: auditoría confirmada junto con el hecho (dominio pacientes), lectura posterior `GET` desde request nueva, baja lógica de pacientes (`DELETE` → fila con `activo=false` visible, R7), opt-in `true`/`false` visible (RN-CO-01), la cadena completa de `POST /api/senas/{id}/vencer` (seña `vencida` + turno `cancelado` + oferta a lista de espera + auditoría; `application/caja.py:441-473`) y aislamiento multi-tenant con el helper filtrando por `tenant_id` del token (R4; precedente `tests/test_pacientes_api.py:157`).
- *Helper con filtro de tenant (R4)*: `assert_persistido(modelo, filtro)` recibe/deriva siempre el `tenant_id` del token usado en la request: lo creado con token de tenant A no se consulta nunca con el tenant B.
- *RED primero (TDD)*: los tests cross-sesión se escriben **antes** del fix y deben fallar hoy ("la liquidación no se persistió…" estilo); el fix los pone en verde.
- *Limpieza*: la sesión compartida del fixture sigue haciendo los DELETE en el teardown; los datos creados desde la sesión nueva usan los mismos fixtures sintéticos (R13) y quedan cubiertos por esa limpieza.

### D4 — Alcance del inventario de endpoints: 28 endpoints mutantes en 4 archivos

- `pacientes.py`: 4 (`POST`, `PATCH /{id}`, `DELETE /{id}`, `PATCH /{id}/optin`).
- `clinica.py`: 8 (PUT ficha, POST evoluciones, POST adjuntos, POST eventos odontograma, POST consentimientos, POST firmar, POST revocar, POST firma pública `/firmar/{token}`).
- `caja.py`: 9 (POST senas, cobrar, cancelación, vencer, POST movimientos, abrir/cerrar/reabrir cierre, cobrar turno).
- `presupuestos.py`: 7 (POST, items, presentar, aceptar, rechazar, finalizar, vincular turno).

El `grep` de verificación (`session\.commit\(\)` por archivo) es la task de auditoría final: los GET no commitean; los POST/PATCH/PUT/DELETE sí terminan en commit.

### D5 — Sin cambios en `application/*` ni en la capa de dominio

Las funciones de `app/application/{pacientes,clinica,caja,presupuestos}.py` siguen con `flush()` (las llama también la reserva pública y otros flujos que ya commitean en su endpoint). Meter `commit()` adentro de la capa application rompería la composición (p. ej. `agenda.crear_turno` llama `generar_sena_pendiente` de `application/caja` dentro de su propia transacción: un commit intermedio la partiría en dos y violaría la atomicidad del alta de turno con seña).

## Risks / Trade-offs

- **[Doble commit donde ya hay commit]** → No aplica: solo se agregan commits a los 4 routers que no lo hacen; los otros 9 no se tocan.
- **[Un endpoint mutante queda sin commit en la auditoría de 28]** → Task de verificación con `grep` por archivo + tests cross-sesión por dominio; cualquier escritura olvidada vuelve a fallar el test de persistencia de ese dominio.
- **[Tests existentes se rompen al commitear la sesión compartida]** → Riesgo real: un `commit()` en la sesión compartida del fixture adelanta la persistencia de datos que el teardown borra igual (los DELETE siguen funcionando). Si algún test dependía de ver estado no-commiteado, se revisa caso por caso; la suite completa es el gate.
- **[Atomicidad parcial a mitad de request si el endpoint lanza después de un commit parcial]** → D2: un solo `commit()` por endpoint, al final de la rama que muta; nunca commits intermedios.
- **[Fix "a medida" que se desincroniza de un futuro refactor UoW]** → D1 deja documentada la consolidación futura; el spec `persistencia-sesiones` describe comportamiento observable (2xx ⇒ persiste), no la mecánica, así que sobrevive a un refactor.
- **[Gobernanza CRÍTICO: tocar HC/turnos/caja]** → Cambio aditivo de una línea por endpoint, sin cambiar lógica; verificación contra DB real (R11) + regresión de la suite completa antes de dar por cerrado.

## Migration Plan

- Sin migraciones de base ni cambios de API: es un fix de código backend puro.
- *Orden de aplicación*: (1) tests cross-sesión RED por dominio; (2) fix por dominio (pacientes → clínica → caja → presupuestos) dejando cada grupo en verde; (3) auditoría grep + suite completa + `ruff`/`mypy` (R2).
- *Rollback*: revertir el commit del change; los endpoints vuelven al comportamiento actual (2xx sin persistir) sin dejar datos inconsistentes porque nunca se confirmaba nada.

## Open Questions

- **Consulta al PO (fuera del alcance, no bloquea)**: idempotencia de reintentos del cliente en POSTs mutantes (doble click / retry tras timeout) — sin regla en la KB; con el fix habilitado un reintento crea filas reales. Detalle en `proposal.md` §Consultas al PO.
- Ninguna otra que cambie los specs, el enfoque o el desglose de tareas. (Consolidación opcional a `UnitOfWork` queda como deuda futura explícita en Non-Goals, no bloquea este change.)

## UI Mockups

Decision: no (no UI) — change backend de una línea por endpoint, sin superficie visual.
