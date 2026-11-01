# Tasks: `c-10-presupuestos-planes`

- [x] **1.1 Modelos `Presupuesto`, `PresupuestoItem`, `PresupuestoTurno` y migración reversible `009_presupuestos_planes`** (TDD)
  - Crear `src/backend/app/domain/presupuesto.py` (`Presupuesto`, `PresupuestoItem`, `PresupuestoTurno`, `EstadoPresupuesto`, `es_transicion_presupuesto_valida`).
  - Crear migración `src/backend/alembic/versions/009_presupuestos_planes.py` con tablas `presupuesto`, `presupuesto_item`, `presupuesto_turno`, constraints, índices y `GRANT/REVOKE` para `turnos_app`. Registrar en `alembic/env.py` y `tests/conftest.py`.
  - Verificar con `tests/test_migracion_009_presupuestos.py`.

- [x] **1.2 Schemas Pydantic v2 estrictos para presupuestos e items (`extra='forbid'`, `R1`, `R8`)** (TDD)
  - Crear `src/backend/app/api/schemas_presupuestos.py` (`PresupuestoItemInput`, `PresupuestoItemRead`, `PresupuestoCreate`, `PresupuestoRead`, `PresupuestoVincularTurnoInput`, `PresupuestoTurnoRead`).
  - Verificar con `tests/test_schemas_presupuestos.py` (rechazo de montos inyectados por el cliente `R8`, validación FDI en `pieza_fdi` y `cantidad >= 1`).

- [x] **2.1 Casos de uso de presupuestos: cálculo OS vs. particular (`RN-OS-01`), guardia invasiva (`RN-CL-04`) y vínculo con turnos** (TDD)
  - Crear `src/backend/app/application/presupuestos.py` (`crear_presupuesto`, `agregar_item_presupuesto`, `obtener_presupuesto`, `listar_presupuestos`, `cambiar_estado_presupuesto`, `aceptar_presupuesto`, `vincular_turno_a_presupuesto`, `listar_turnos_presupuesto`).
  - Verificar con `tests/test_presupuestos_negocio.py`.

- [x] **3.1 Endpoints `/api/presupuestos` CRUD + items + transiciones + `/turnos`** (TDD)
  - Crear `src/backend/app/api/routers/presupuestos.py` protegido por `Recurso.PRESUPUESTOS` y registrarlo en `src/backend/app/main.py` y `tests/conftest.py`.
  - Verificar con `tests/test_presupuestos_api.py`.

- [x] **3.2 Calidad (`ruff`, `mypy`, suite completa) y documentación (`README.md`, `CHANGES.md`)**
  - Actualizar `README.md` y `CHANGES.md` documentando `C-10`, ejecutar `ruff check`, `ruff format --check`, `mypy` y `pytest` completo.
