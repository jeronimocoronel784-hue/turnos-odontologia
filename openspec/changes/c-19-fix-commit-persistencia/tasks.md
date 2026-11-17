# Tasks

> TDD estricto por tarea: **RED** (test cross-sesión que falla hoy) → **GREEN** (agregar `await session.commit()`) → **TRIANGULATE** (≥2 casos por comportamiento, R11) → **REFACTOR**. Gobernanza CRÍTICO: fix quirúrgico de una línea por endpoint, sin tocar `deps.sesion_db`, `application/*`, contratos ni los 9 routers que ya commitean. Cada tarea se cierra con su verificación en verde; sin PHI en tests ni logs (R9/R13: fixtures sintéticas siempre).

## 1. Guard de persistencia cross-sesión (RED)

- [x] 1.1 Crear `tests/test_persistencia_commit.py` con helper `assert_persistido(modelo, filtro)` que abre un **engine y sesión nuevos** con `create_engine_for(db_url)` (mismo `db_url` de la fixture) y consulta la fila **filtrando siempre por el `tenant_id` del token usado en la request (R4)**, replicando el patrón de `tests/test_liquidaciones_api.py:741-763`; verificar con un test smoke que el helper consulta sin errores.
- [x] 1.2 Escribir los tests RED de **pacientes**: alta con `POST /api/pacientes` → `201` y la fila + ficha clínica 1:1 visibles desde la sesión nueva; `PATCH /api/pacientes/{id}` → `200` y los cambios visibles desde la sesión nueva; verificar que **fallan hoy** con mensaje tipo "no se persistió" (RED documentado).
- [x] 1.3 Escribir los tests RED de **clínica**: `POST .../evoluciones` → `201` visible desde sesión nueva; `POST /api/odontograma/{id}/eventos` → `201` visible desde sesión nueva; verificar que fallan hoy (RED).
- [x] 1.4 Escribir los tests RED de **caja**: `POST /api/senas` → `201` y `POST /api/caja/movimientos` → `201` visibles desde sesión nueva; verificar que fallan hoy (RED).
- [x] 1.5 Escribir los tests RED de **presupuestos**: `POST /api/presupuestos` → `201` y transición `POST /{id}/presentar` → `200` visibles desde sesión nueva; verificar que fallan hoy (RED).
- [x] 1.6 Escribir los tests RED de **baja lógica y opt-in de pacientes**: `DELETE /api/pacientes/{id}` → `200` y desde sesión nueva la fila sigue existiendo con `activo=false` (R7); `PATCH /api/pacientes/{id}/optin` con `true` y luego `false` → `200` y el último valor visible desde sesión nueva (RN-CO-01); verificar que fallan hoy (RED).
- [x] 1.7 Escribir el test RED de **cadena de vencimiento de seña**: `POST /api/senas/{id}/vencer` → `2xx` y desde sesión nueva se ven juntos seña `vencida`, turno `cancelado` (RN-AG-07), entrada de lista de espera actualizada por la oferta del slot (RN-LE-01) y la fila de auditoría (RN-PA-01) — patrón `application/caja.py:441-473`; verificar que falla hoy (RED). Cubre también el cobro de seña (`POST /api/senas/{id}/cobrar` → seña `cobrada` + movimiento de ingreso visibles desde sesión nueva) que `spec.md` ya especificaba.
- [x] 1.8 Escribir el test RED de **aislamiento multi-tenant**: entidad creada con token de tenant A visible desde sesión nueva con el `tenant_id` de A e **invisible** con el `tenant_id` de B (precedente `tests/test_pacientes_api.py:157`); verificar el caso negativo y el positivo (≥2 escenarios, R11).

## 2. Fix pacientes (GREEN)

- [x] 2.1 Agregar `await session.commit()` después de la auditoría en los 4 endpoints mutantes de `src/backend/app/api/routers/pacientes.py` (crear, actualizar, baja lógica, opt-in) — commit solo en la rama que mutó; verificar que los tests 1.2 y 1.6 pasan (GREEN) y que los early-returns sin escritura no commitean.
- [x] 2.2 Triangulate pacientes: caso borde cross-sesión — operación fallida (`POST` con DNI duplicado → `409`) no deja paciente nuevo ni entrada de auditoría visibles desde la sesión nueva; verificar que el test pasa y que ≥2 casos por comportamiento quedan cubiertos (happy path + borde).

## 3. Fix clínica (GREEN)

- [x] 3.1 Agregar `await session.commit()` en los 8 endpoints mutantes de `src/backend/app/api/routers/clinica.py` (PUT ficha, evoluciones, adjuntos, eventos de odontograma, consentimientos, firmar, revocar y firma pública `/firmar/{token}`); verificar que los tests 1.3 pasan (GREEN) y `pytest tests/test_clinica_api.py tests/test_clinica_negocio.py` sigue en verde.
- [x] 3.2 Triangulate clínica: caso borde cross-sesión — evolución rechazada (p. ej. `404` por paciente inexistente o `403` por rol recepción en escritura) no deja registro ni auditoría visibles desde la sesión nueva; verificar que el test pasa (≥2 casos por comportamiento).

## 4. Fix caja (GREEN)

- [x] 4.1 Agregar `await session.commit()` en los 9 endpoints mutantes de `src/backend/app/api/routers/caja.py` (señas: crear/cobrar/cancelación/vencer; movimientos; cierres: abrir/cerrar/reabrir; cobro de turno); verificar que los tests 1.4 y 1.7 pasan (GREEN — incluida la cadena vencer → turno `cancelado` → lista de espera → auditoría) y que `pytest tests/test_caja_api.py tests/test_caja_negocio.py` sigue en verde.
- [x] 4.2 Triangulate caja: caso borde cross-sesión — cerrar un cierre ya cerrado (`409`, cierre cerrado inmutable y reapertura solo Dueño según `knowledge-base/04_modelo_de_datos.md:105` y `knowledge-base/07_flujos_principales.md:71`) no deja cambios de estado visibles desde la sesión nueva; verificar que el test pasa (≥2 casos por comportamiento).

## 5. Fix presupuestos (GREEN)

- [x] 5.1 Agregar `await session.commit()` en los 7 endpoints mutantes de `src/backend/app/api/routers/presupuestos.py` (crear, items, presentar, aceptar, rechazar, finalizar, vincular turno); verificar que los tests 1.5 pasan (GREEN) y que `pytest tests/test_presupuestos_api.py tests/test_presupuestos_negocio.py` sigue en verde.
- [x] 5.2 Triangulate presupuestos: caso borde cross-sesión — aceptar presupuesto con prestación invasiva sin consentimiento (`409` RN-CL-04) no deja cambio de estado visibles desde la sesión nueva; verificar que el test pasa (≥2 casos por comportamiento).

## 6. Auditoría transversal y cierre (verificación integral)

- [x] 6.1 Test de auditoría en la misma transacción: alta de paciente `201` → desde la sesión nueva se ve tanto el paciente como su entrada en `auditoria`; y alta fallida no deja auditoría huérfana; verificar ambos casos en verde.
- [x] 6.2 Test de lectura posterior: `GET` desde una **request nueva** (cliente HTTP nuevo) devuelve lo escrito por un `2xx` previo; `GET` del recurso de una **alta** fallida responde `404 Not Found`; `GET` de un recurso existente tras una **edición** fallida devuelve el estado anterior (casos separados según `spec.md`); verificar en verde.
- [x] 6.3 Aislamiento multi-tenant del helper: el helper `assert_persistido` filtra por `tenant_id` del token y el test 1.8 pasa — lo creado con token de tenant A es invisible con el `tenant_id` de B y visible con el de A (R4); verificar ambos casos en verde.
- [x] 6.4 Auditoría de cobertura con `grep`: confirmar que los POST/PATCH/PUT/DELETE de los 4 archivos terminan en `session.commit()` y que los GET no commitean; verificar con `grep -c "session\.commit\(\)"` por archivo esperando 4 / 8 / 9 / 7 ocurrencias respectivamente.
- [x] 6.5 Correr la suite completa de backend (`pytest tests/`, contra DB real vía `DATABASE_URL_TEST` en CI/Docker, R11) y `ruff check` + `mypy` sobre `src/backend` (R2); verificar todo en verde y registrar la salida en el resumen del apply.
- [x] 6.6 Verificación manual contra PostgreSQL real (patrón de C-16 task 7.2, datos sintéticos): `POST /api/pacientes` con un cliente y `SELECT` en una sesión/psql distinto muestra la fila; repetir con un movimiento de caja; documentar la salida como evidencia de cierre.

## Workflow follow-up

- Actualizar `CHANGES.md` (estado de C-19 y desbloqueo de las referencias de C-16/C-17 en su sección "Estado") — lo hace el orquestador en tarea aparte.
- Push a GitHub (R12) — lo hace el orquestador en coordinación con la higiene de commits.
- Archivar el change (`openspec archive`) tras la revisión y la actualización de specs.
