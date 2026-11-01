# Tasks: `c-11-caja-senas`

- [ ] **1.1 Modelos `Sena`, `MovimientoCaja`, `CierreCaja` y migración reversible `010_caja_senas`** (TDD)
  - Crear `src/backend/app/domain/caja.py` (`Sena`, `EstadoSena`, `es_transicion_sena_valida`, `MovimientoCaja`, `TipoMovimientoCaja`, `MedioPago`, `CierreCaja`, `EstadoCierreCaja`).
  - Crear migración `src/backend/alembic/versions/010_caja_senas.py` con tablas `sena`, `cierre_caja`, `movimiento_caja`, constraints, índices y `GRANT/REVOKE` para `turnos_app`. Registrar en `alembic/env.py` y `tests/conftest.py`.
  - Verificar con `tests/test_migracion_010_caja_senas.py`.

- [ ] **1.2 Schemas Pydantic v2 estrictos para señas, movimientos y cierres de caja (`extra='forbid'`, `R1`, `R8`)** (TDD)
  - Crear `src/backend/app/api/schemas_caja.py` (`SenaCreate`, `SenaCobrarInput`, `SenaResolverCancelacionInput`, `SenaRead`, `MovimientoCajaCreate`, `MovimientoCajaRead`, `CierreCajaAbrirInput`, `CierreCajaCerrarInput`, `CierreCajaReabrirInput`, `CierreCajaRead`, `LiquidacionTurnoRead`, `CobrarTurnoInput`).
  - Verificar con `tests/test_schemas_caja.py`.

- [ ] **2.1 Casos de uso de señas (`RN-PA-01/02/04`), saldo de atención (`Flujo 4`) y caja diaria con cierre/reapertura (`RN-PA-05`)** (TDD)
  - Crear `src/backend/app/application/caja.py` e integrar la auto-generación de `Sena` en `crear_turno` (`src/backend/app/application/agenda.py`) cuando `prestacion.requiere_sena` es `True`.
  - Verificar con `tests/test_caja_negocio.py`.

- [ ] **3.1 Endpoints `/api/senas*` y `/api/caja/*` con RBAC (`Recurso.CAJA` y `Accion.REABRIR_CIERRE`)** (TDD)
  - Crear `src/backend/app/api/routers/caja.py` y registrarlo en `src/backend/app/main.py` y `tests/conftest.py`.
  - Verificar con `tests/test_caja_api.py` (recepción opera caja y cierra, recibe `403` al intentar reabrir; dueño reabre con `200` y auditoría; flujo completo de seña y cobro de saldo).

- [ ] **3.2 Calidad (`ruff`, `mypy`, suite completa) y documentación (`README.md`, `CHANGES.md`)**
  - Actualizar `README.md` y `CHANGES.md` documentando `C-11`, ejecutar `ruff check`, `ruff format --check`, `mypy` y `pytest` completo.
