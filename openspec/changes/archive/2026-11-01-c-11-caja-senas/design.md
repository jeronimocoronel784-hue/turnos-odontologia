# Design: `c-11-caja-senas`

## UI Mockups
Decision: no (no UI — este change implementa modelos, migración, lógica de negocio y endpoints backend de señas y caja; la interfaz de caja corresponde a C-17).

## Context
`C-11` implementa la Fase 4 (Dinero — parte 1: señas y caja diaria sin Mercado Pago, que entra en `C-12`) según `04_modelo_de_datos.md` (§Sena, §Caja / Movimiento), `05_reglas_de_negocio.md` (`RN-PA-01..05`) y `07_flujos_principales.md` (Flujo 1 paso 6 y Flujo 4).

## Decisions

### D1. Auto-generación y grafo de `Sena` (`RN-PA-01`, `RN-PA-02`, `RN-PA-04`)
- Cuando `crear_turno` (`agenda.py`) crea un turno para una `Prestacion` con `requiere_sena == True`, crea también la fila `Sena` en estado `pendiente` con `monto = prestacion.monto_sena` y `vence_at = ahora + 24h` (si no existiera ya).
- Estados (`EstadoSena`): `pendiente`, `cobrada`, `aplicada`, `devuelta`, `vencida`.
- Grafo (`es_transicion_sena_valida`):
  - `pendiente -> cobrada | vencida | devuelta`
  - `cobrada -> aplicada | devuelta`
- Al cobrar una seña (`cobrar_sena`): pasa a `cobrada`, actualiza `turno.sena_cobrada = True` y crea un `MovimientoCaja` (`tipo="ingreso"`, `monto=sena.monto`, vinculado al `CierreCaja` abierto si existe).
- Si la seña vence impaga (`vencer_sena_impaga`): pasa a `vencida` y cancela el turno (`cambiar_estado_turno(..., EstadoTurno.CANCELADO)`), lo que libera el slot y dispara `ofrecer_hueco_lista_espera`.

### D2. Liquidación del turno y aplicación de seña (`Flujo 4`, `R8`)
- `calcular_liquidacion_turno` obtiene `precio_particular` de la prestación, calcula `cobertura_os` usando `calcular_montos_item_presupuesto` (convenio vigente del paciente si se indica `obra_social`), busca si el turno tiene una `Sena` en estado `cobrada` (o `aplicada`) y devuelve `saldo = max(0, precio - cobertura_os - monto_sena_cobrada)`.
- `cobrar_saldo_turno` registra el `MovimientoCaja` por el `saldo` (si `saldo > 0`) y, si había una `Sena` en `cobrada`, la transiciona a `aplicada`.

### D3. `CierreCaja` inmutable y reapertura por `Accion.REABRIR_CIERRE` (`US-030`)
- Un consultorio puede tener un `CierreCaja` en estado `abierto` para una fecha dada. Los nuevos `MovimientoCaja` se asocian automáticamente al cierre abierto vigente (o al `cierre_id` indicado si está `abierto`; si está `cerrado`, se rechaza con `409 Conflict`).
- Al cerrar (`cerrar_caja`), se suman todos los movimientos del cierre (`ingresos - egresos`) para fijar `total_sistema`, se calcula `diferencia = total_contado - total_sistema` y se pasa a `cerrado`.
- Reabrir (`reabrir_caja`) está protegido por `requiere(Recurso.CAJA, Accion.REABRIR_CIERRE)` (solo `DUENO` en `rbac.py`), requiere motivo y registra `Auditoria` con `antes` y `despues`.
