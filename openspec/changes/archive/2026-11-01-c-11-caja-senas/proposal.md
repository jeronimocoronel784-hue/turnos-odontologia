# Proposal: `c-11-caja-senas`

## Why
El consultorio odontológico necesita gestionar señas atadas a la cita (`pendiente → cobrada → aplicada | devuelta`, más `vencida`) para reducir el ausentismo (`RN-PA-01..05`, `US-030`, `US-031`), así como llevar la caja diaria con movimientos por medio de pago (`efectivo`, `debito`, `credito`, `transferencia`, `mp`), cierre con diferencia visible (`total_sistema` vs. `total_contado`), inmutabilidad de movimientos vinculados a cierres cerrados y reapertura exclusiva para el rol `DUENO` con auditoría obligatoria (`RN-SE-01`).

## What Changes
- **Dominio y Migración `010_caja_senas`**:
  - `Sena` (`sena`): relación 1:1 con `turno_id` (`UniqueConstraint("turno_id")`), `monto`, `estado` (`pendiente`, `cobrada`, `aplicada`, `devuelta`, `vencida`), `mp_payment_id` (nullable, para `C-12`), `vence_at` (nullable).
  - `CierreCaja` (`cierre_caja`): `fecha`, `total_sistema`, `total_contado`, `diferencia` (`total_contado - total_sistema`), `estado` (`abierto`, `cerrado`), `abierto_por`, `cerrado_por`, `cerrado_at`, `reabierto_motivo`.
  - `MovimientoCaja` (`movimiento_caja`): `tipo` (`ingreso`, `egreso`), `concepto`, `medio` (`efectivo`, `debito`, `credito`, `transferencia`, `mp`), `monto`, `turno_id` (nullable), `sena_id` (nullable), `cobro_mp_id` (nullable, para `C-12`), `cierre_id` (nullable), `created_by`, `created_at` (append-only, `R7`).
  - Permisos `GRANT/REVOKE` para `turnos_app` en `010_caja_senas.py`.
- **Reglas de Negocio (`RN-PA-01`, `RN-PA-02`, `RN-PA-04`, `RN-PA-05`, `RN-SE-01`, `R7`, `R8`)**:
  - Auto-generación de `Sena` en `crear_turno` (`agenda.py`): cuando `prestacion.requiere_sena == True`, se crea automáticamente la fila en `sena` en estado `pendiente` con `monto = prestacion.monto_sena` y `vence_at` (`RN-PA-02`).
  - Máquina de estados de `Sena` (`es_transicion_sena_valida`): `pendiente -> cobrada | vencida | devuelta`, `cobrada -> aplicada | devuelta`. Al marcar `cobrada`, actualiza `turno.sena_cobrada = True` y genera automáticamente un `MovimientoCaja` de ingreso (`RN-PA-01`, `RN-PA-05`).
  - Vencimiento de seña impaga (`vencer_sena_impaga`): pasa la seña a `vencida`, cancela el turno liberando el slot y dispara `ofrecer_hueco_lista_espera` (Flujo 1 paso 6).
  - Cancelación de turno con seña cobrada (`resolver_sena_en_cancelacion`, `RN-PA-04`): dentro del término (`cancelacion_hs`) pasa a `devuelta` (con movimiento de egreso); fuera de término o por `ausente` se retiene y pasa a `aplicada`.
  - Cálculo de saldo al cobrar atención (`calcular_liquidacion_turno`, Flujo 4): `saldo = max(0, precio_particular - cobertura_os - sena_cobrada)` calculado siempre en servidor (`R8`).
  - `CierreCaja`: calcula `total_sistema` sumando `ingresos - egresos` de los movimientos vinculados, registra `diferencia = total_contado - total_sistema`, bloquea cualquier mutación/adición sobre un cierre `cerrado` y restringe la reapertura (`POST /api/caja/cierre/{id}/reabrir`) exclusivamente a `Accion.REABRIR_CIERRE` (rol `DUENO`) con auditoría obligatoria.
- **API REST (`/api/senas` y `/api/caja/*`)**:
  - Protegidos por `Recurso.CAJA`:
    - `GET /api/senas`, `POST /api/senas`, `POST /api/senas/{id}/cobrar`, `POST /api/senas/{id}/vencer`, `POST /api/senas/{id}/resolver-cancelacion`
    - `GET /api/caja/liquidacion-turno/{turno_id}`, `POST /api/caja/cobrar-turno/{turno_id}`
    - `GET /api/caja/movimientos`, `POST /api/caja/movimientos`
    - `GET /api/caja/cierres`, `POST /api/caja/cierre/abrir`, `POST /api/caja/cierre/{id}/cerrar`, `POST /api/caja/cierre/{id}/reabrir` (`Accion.REABRIR_CIERRE`, solo `DUENO`)

## Capabilities
### New Capabilities
- `caja-senas`: Señas vinculadas al turno con grafo de estados (`RN-PA-01/02/04`), movimientos de caja por medio de pago (`RN-PA-05`), cálculo de saldo en servidor (`Flujo 4`, `R8`) y cierre diario inmutable con reapertura exclusiva para Dueño (`US-030`, `US-031`).

## Impact
- **Governance**: `CRITICO` (dinero, señas, conciliación e inmutabilidad de caja).
- **Dependencias**: `C-06` (`agenda-turnos`). Desbloquea `C-12` (`mercadopago-webhooks`) y `C-14` (`auditoria-exportacion`).
