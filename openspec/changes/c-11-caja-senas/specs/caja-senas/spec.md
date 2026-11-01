# caja-senas Specification

## Purpose
Gestionar las señas vinculadas a los turnos (`pendiente → cobrada → aplicada | devuelta | vencida`), el cálculo en servidor del saldo de atención (`precio - cobertura_os - sena_cobrada`), los movimientos de caja por medio de pago y el cierre de caja diario inmutable con reapertura exclusiva para el rol `DUENO` auditada (`RN-PA-01..05`, `R7`, `R8`).

## ADDED Requirements

### Requirement: Ciclo de vida de la seña vinculada al turno y política de cancelación
El sistema MUST generar una `Sena` en estado `pendiente` cuando se reserva un turno cuya prestación tiene `requiere_sena = True` (`RN-PA-02`). Un turno con seña exigible impaga MUST NOT pasar a `confirmado` (`RN-PA-01`). Al cobrarse la seña, MUST pasar a `cobrada`, habilitar la confirmación del turno y registrar su `MovimientoCaja` (`RN-PA-05`). Ante cancelación dentro de término, la seña cobrada MUST pasar a `devuelta`; fuera de término o por inasistencia (`ausente`), MUST retenerse pasando a `aplicada` (`RN-PA-04`).

#### Scenario: Cobro de seña habilita confirmar turno y cancelación en/fuera de término aplica RN-PA-04
- **GIVEN** un turno reservado para una prestación con `requiere_sena = True` y `monto_sena = 10000.00`
- **WHEN** se cobra la seña y luego se evalúa cancelación dentro de término vs. fuera de término
- **THEN** el cobro genera el movimiento de ingreso y marca `sena_cobrada = True`; cancelar en término pasa la seña a `devuelta` y cancelar fuera de término la pasa a `aplicada`.

### Requirement: Cálculo de saldo de atención con descuento de cobertura OS y seña cobrada
El sistema MUST calcular en el servidor el saldo a cobrar de un turno como `saldo = max(0, precio_particular - cobertura_os - sena_cobrada)` (`R8`, Flujo 4). Al cobrar el saldo del turno, el sistema MUST registrar el `MovimientoCaja` por el medio elegido y pasar la seña `cobrada` a estado `aplicada`.

#### Scenario: Cobro de atención descuenta cobertura de obra social y seña previa
- **GIVEN** un turno con prestación de `50000.00`, cobertura OS vigente de `20000.00` y seña `cobrada` de `10000.00`
- **WHEN** recepción consulta la liquidación y cobra el saldo del turno
- **THEN** el sistema informa `saldo = 20000.00`, crea un movimiento de ingreso por `20000.00` y marca la seña como `aplicada`.

### Requirement: Cierre diario de caja con diferencia visible, inmutabilidad y reapertura exclusiva Dueño
El sistema MUST calcular `total_sistema` a partir de los movimientos vinculados al cierre, registrar `diferencia = total_contado - total_sistema` al cerrar e impedir agregar o modificar movimientos sobre un `CierreCaja` en estado `cerrado` (`RN-PA-05`). La reapertura de un cierre cerrado MUST estar restringida exclusivamente al rol `DUENO` (`Accion.REABRIR_CIERRE`) y dejar registro en `Auditoria` (`RN-SE-01`).

#### Scenario: Cierre de caja bloquea nuevos movimientos y recepción recibe 403 al intentar reabrir
- **GIVEN** un cierre de caja abierto con movimientos por `30000.00` que recepción cierra declarando `total_contado = 29500.00`
- **WHEN** recepción intenta reabrir el cierre y luego el usuario `DUENO` solicita reabrirlo con motivo
- **THEN** el cierre registra `diferencia = -500.00`, el intento de recepción responde `403 Forbidden` y la reapertura del `DUENO` responde `200 OK` dejando evento en `Auditoria`.
