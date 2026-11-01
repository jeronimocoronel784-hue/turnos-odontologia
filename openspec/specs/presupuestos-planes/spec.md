# presupuestos-planes Specification

## Purpose
Gestionar presupuestos y planes de tratamiento odontológico con cálculo automático en servidor de cobertura de obra social vs. a cargo del paciente (`RN-OS-01`, `R8`), validación de consentimiento informado firmado al aceptar planes con prestaciones invasivas (`RN-CL-04`) y vinculación N–N con turnos hasta finalizar el plan (`US-022`).

## Requirements

### Requirement: Cálculo en servidor de items con cobertura de obra social vigente o particular
El sistema MUST calcular en el servidor los importes `precio_unit`, `cobertura_os` y `a_cargo = (precio_unit * cantidad) - cobertura_os` de cada `PresupuestoItem` y los totales de `Presupuesto` (`R8`, `RN-OS-01`). Cuando exista una `CoberturaOS` activa y vigente para la obra social y la prestación, MUST aplicarse dicha cobertura; cuando no exista cobertura vigente, MUST facturarse como particular (`cobertura_os = 0`).

#### Scenario: Presupuesto con cobertura vigente aplica arancel/copago y sin cobertura factura particular
- **GIVEN** una prestación con precio particular `40000.00` y una `CoberturaOS` activa vigente para `"OSDE"` con arancel cubierto `30000.00`
- **WHEN** se crea un presupuesto para `"OSDE"` con 1 unidad de esa prestación y otro presupuesto para `"SWISS"` sin convenio vigente
- **THEN** el primero registra `cobertura_os = 30000.00` y `a_cargo = 10000.00`, mientras que el segundo registra `cobertura_os = 0.00` y `a_cargo = 40000.00`.

### Requirement: Exigencia de consentimiento firmado al aceptar presupuesto con prestación invasiva
El sistema MUST verificar al aceptar un `Presupuesto` (`POST /api/presupuestos/{id}/aceptar`) si alguno de sus items corresponde a una `Prestacion` con `invasiva = True` (`RN-CL-04`). Si existe al menos una prestación invasiva sin `Consentimiento` firmado y no revocado para el paciente, el sistema MUST rechazar la aceptación con `409 Conflict`.

#### Scenario: Rechazo al aceptar presupuesto invasivo sin consentimiento y éxito tras firmar
- **GIVEN** un presupuesto en estado `presentado` que incluye una prestación con `invasiva = True`
- **WHEN** se intenta aceptar sin consentimiento firmado y luego se firma el consentimiento y se vuelve a aceptar
- **THEN** el primer intento responde `409 Conflict` y el segundo transiciona el presupuesto a `aceptado`.

### Requirement: Vinculación de turnos al plan de tratamiento y avance de estados hasta finalizado
El sistema MUST permitir vincular turnos (`Turno`) del paciente a un `Presupuesto` mediante `PresupuestoTurno`, pasando el presupuesto a `en_curso` al asociar su primera cita y permitiendo cerrarlo en `finalizado` al completar la atención (`US-022`).

#### Scenario: Vincular turno pasa el presupuesto aceptado a en_curso y permite finalizarlo
- **GIVEN** un presupuesto en estado `aceptado` y un turno activo del mismo paciente
- **WHEN** se vincula el turno mediante `POST /api/presupuestos/{id}/turnos` y luego se invoca `POST /api/presupuestos/{id}/finalizar`
- **THEN** el presupuesto pasa primero a `en_curso`, lista el turno vinculado y finalmente queda en estado `finalizado`.
