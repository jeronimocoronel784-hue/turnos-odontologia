# Spec Delta: `obras-sociales-liquidacion`

## Purpose
Resolver la cobertura de obra social de cada prestación según el arancel vigente y liquidar mensualmente por obra social los turnos finalizados, con control de débitos, unicidad de turno liquidado y exportación CSV/JSON (`RN-OS-01`, `RN-OS-02`, `RN-OS-03`, `US-040`, `US-041`).

## ADDED Requirements

### Requirement: Resolución de cobertura vigente y cálculo del monto a cargo
El sistema MUST resolver en el servidor la cobertura de una prestación contra el padrón `CoberturaOS` activo y vigente a la fecha de referencia, y MUST calcular `monto_a_cargo = precio_particular - cobertura` sin aceptar montos provistos por el cliente (`R8`). Si no existe cobertura vigente para la obra social indicada, MUST informar modo particular con `cobertura = 0` y `monto_a_cargo = precio_particular` (`RN-OS-01`).

#### Scenario: Cobertura vigente aplica el arancel del convenio
- **GIVEN** una prestación con `precio_particular = 50000.00` y un convenio activo de la obra social con `arancel = 30000.00` vigente a la fecha de referencia
- **WHEN** recepción consulta la cobertura de esa prestación para esa obra social
- **THEN** el sistema responde `precio_particular = 50000.00`, `cobertura = 30000.00`, `monto_a_cargo = 20000.00` y estado de arancel `vigente`

#### Scenario: Sin cobertura vigente se factura como particular
- **GIVEN** una prestación con `precio_particular = 50000.00` y sin convenio registrado para la obra social indicada
- **WHEN** recepción consulta la cobertura de esa prestación para esa obra social
- **THEN** el sistema responde modo particular con `cobertura = 0.00`, `monto_a_cargo = 50000.00` y estado de arancel `sin_cobertura`

### Requirement: Alerta de arancel vencido con uso del arancel más reciente
Cuando el único convenio registrado para la obra social y la prestación tenga `vigencia_hasta` anterior a la fecha de referencia, el sistema MUST responder con la advertencia explícita de arancel vencido y MUST calcular la cobertura con el arancel más reciente de ese convenio en lugar de facturar como particular (Flujo 5, `RN-OS-01`). La advertencia MUST viajar con la respuesta para que recepción la informe al paciente.

#### Scenario: Arancel vencido alerta y usa el arancel más reciente
- **GIVEN** un convenio con `arancel = 30000.00` y `vigencia_hasta` del 31/10/2026
- **WHEN** se consulta la cobertura con fecha de referencia 15/11/2026
- **THEN** el sistema responde `arancel_vencido = true`, `vigencia_hasta = 2026-10-31`, `cobertura = 30000.00` y un mensaje de advertencia en rioplatense

#### Scenario: La liquidación conserva la marca de arancel vencido por turno
- **GIVEN** una liquidación generada sobre turnos cuyo arancel estaba vencido al momento del cálculo
- **WHEN** se consulta el detalle de la liquidación
- **THEN** cada fila afectada expone `arancel_vencido = true` para revisión antes de presentar

### Requirement: Alta de liquidación con turnos finalizados del período
El sistema MUST crear una liquidación en estado `borrador` para una obra social y un período `yyyymm`, incluyendo únicamente turnos en estado `finalizado` cuyo inicio caiga dentro del período y que tengan convenio registrado para esa obra social, calculando `monto_reclamado` por turno con el arancel resuelto (`RN-OS-02`). El sistema MUST NOT incluir turnos `pendiente`, `confirmado`, `presente`, `cancelado`, `ausente` ni `reprogramado`.

#### Scenario: Se incluyen los turnos finalizados con cobertura del período
- **GIVEN** tres turnos finalizados en noviembre de 2026 con convenio de la obra social y un turno finalizado en octubre de 2026
- **WHEN** se crea la liquidación de la obra social para el período `202611`
- **THEN** el borrador contiene exactamente los tres turnos de noviembre con su `monto_reclamado`

#### Scenario: Un turno no finalizado no entra en la liquidación
- **GIVEN** un turno en estado `cancelado` y otro en estado `presente` dentro del período
- **WHEN** se crea la liquidación de la obra social para ese período
- **THEN** el borrador no contiene ninguno de esos dos turnos

#### Scenario: Turnos sin convenio con la obra social quedan fuera
- **GIVEN** un turno finalizado del período cuya prestación no tiene convenio con la obra social liquidada
- **WHEN** se crea la liquidación de esa obra social
- **THEN** el turno queda fuera del borrador y el sistema informa cuántos turnos del período quedaron sin cobertura

### Requirement: Unicidad del turno en una liquidación abierta por obra social y período
Un turno MUST figurar en una sola liquidación abierta (`borrador`, `presentada` o `con_debitos`) por obra social y período. El sistema MUST rechazar con `409 Conflict` cualquier intento de incluirlo en una segunda liquidación abierta y MUST garantizarlo además como constraint de base de datos (`RN-OS-02`).

#### Scenario: Doble liquidación del mismo turno es rechazada
- **GIVEN** un turno finalizado ya incluido en la liquidación `202611` de la obra social en estado `presentada`
- **WHEN** se intenta crear otra liquidación `202611` de la misma obra social que incluya ese turno
- **THEN** el sistema responde `409 Conflict`, no crea la segunda liquidación y no duplica el turno

#### Scenario: Anular la liquidación libera el turno
- **GIVEN** una liquidación en `borrador` que contiene un turno finalizado
- **WHEN** la liquidación se anula y se crea una nueva liquidación para la misma obra social y período
- **THEN** el turno puede incluirse en la nueva liquidación sin violar el constraint

### Requirement: Registro de débitos sobre el borrador
El sistema MUST permitir registrar sobre una liquidación `borrador` el `monto_reconocido` por turno y MUST exigir un `debito_motivo` no vacío cuando lo reconocido sea menor a lo reclamado (`US-041`). Los totales MUST recalcularse en el servidor como suma de `monto_reclamado` y suma de `monto_reconocido`, sin confiar en totales del cliente (`R8`).

#### Scenario: Débito con motivo actualiza los totales
- **GIVEN** un borrador con un turno reclamado por `20000.00`
- **WHEN** se registra `monto_reconocido = 15000.00` con `debito_motivo = "Arancel fuera de nomenclador"`
- **THEN** el detalle queda con el débito, `total` sigue en `20000.00` y `total_reconocido` pasa a `15000.00`

#### Scenario: Débito sin motivo es rechazado
- **GIVEN** un borrador con un turno reclamado por `20000.00`
- **WHEN** se intenta registrar `monto_reconocido = 15000.00` sin `debito_motivo`
- **THEN** el sistema responde `422` y el detalle no cambia

### Requirement: Presentación del borrador e inmutabilidad del detalle
Cerrar una liquidación MUST transicionar `borrador → presentada` sólo si tiene al menos un turno con `monto_reclamado` mayor a cero, y MUST fijar el detalle como inmutable. Cualquier intento de editar débitos de una liquidación ya presentada MUST rechazarse con `409 Conflict`.

#### Scenario: Cierre exitoso de un borrador con turnos
- **GIVEN** un borrador con dos turnos y total mayor a cero
- **WHEN** el usuario cierra la liquidación
- **THEN** pasa a estado `presentada` y registra quién y cuándo la presentó

#### Scenario: Borrador vacío no se puede presentar
- **GIVEN** un borrador sin turnos
- **WHEN** el usuario intenta cerrarlo
- **THEN** el sistema responde `422` y la liquidación sigue en `borrador`

#### Scenario: Editar débitos de una liquidación presentada es rechazado
- **GIVEN** una liquidación en estado `presentada`
- **WHEN** se intenta modificar el `monto_reconocido` de un turno
- **THEN** el sistema responde `409 Conflict` y el detalle queda intacto

### Requirement: Registro del resultado informado por la obra social
El sistema MUST registrar la respuesta de la obra social transicionando `presentada → pagada` cuando reconoce el total reclamado, o `presentada → con_debitos` cuando reconoce menos, guardando `monto_reconocido` y `debito_motivo` por turno y el `total_reconocido` de la liquidación (`US-041`).

#### Scenario: Resultado con recortes deja la liquidación con débitos
- **GIVEN** una liquidación `presentada` con total reclamado `20000.00`
- **WHEN** se registra un resultado donde la obra social reconoce `15000.00` con motivo de débito
- **THEN** la liquidación pasa a `con_debitos` y expone `total_reconocido = 15000.00` con el motivo por turno

#### Scenario: Resultado que reconoce el total cierra como pagada
- **GIVEN** una liquidación `presentada` con total reclamado `20000.00`
- **WHEN** se registra un resultado que reconoce `20000.00`
- **THEN** la liquidación pasa a `pagada` con `total_reconocido = 20000.00`

### Requirement: Anulación por baja lógica sin borrado físico
El sistema MUST permitir anular únicamente una liquidación en estado `borrador` mediante baja lógica a estado `anulada`, conservando la cabecera y su detalle. MUST rechazar la anulación de una liquidación `presentada`, `pagada` o `con_debitos`, y MUST NOT eliminar físicamente ninguna liquidación ni fila de detalle (`R7`, `RN-SE-01`).

#### Scenario: Anulación de un borrador conserva el historial
- **GIVEN** un borrador con dos turnos
- **WHEN** el usuario anula la liquidación
- **THEN** la liquidación pasa a `anulada`, sus dos filas de detalle siguen existiendo y el turno queda liberado para otra liquidación

#### Scenario: Una liquidación presentada no se anula
- **GIVEN** una liquidación en estado `presentada`
- **WHEN** el usuario intenta anularla
- **THEN** el sistema responde `409 Conflict` y la liquidación conserva su estado

### Requirement: Exportación CSV y JSON del detalle con débitos
El sistema MUST generar en el servidor la exportación de una liquidación en formato CSV o JSON, incluyendo cabecera (obra social, período, estado, totales) y una fila por turno con fecha, prestación, `monto_reclamado`, `monto_reconocido` y `debito_motivo` (`RN-OS-03`, `R8`). La exportación MUST NOT incluir presentación electrónica ni enviar el archivo a la obra social en v1.

#### Scenario: Exportación CSV con débitos
- **GIVEN** una liquidación `con_debitos` con un turno reconocido parcialmente
- **WHEN** el usuario exporta en formato CSV
- **THEN** el archivo descargado contiene una fila por turno con los montos y el `debito_motivo` del recorte

#### Scenario: Exportación JSON con la cabecera y el detalle
- **GIVEN** una liquidación `presentada` con tres turnos
- **WHEN** el usuario exporta en formato JSON
- **THEN** la respuesta incluye la cabecera de la liquidación y una lista con los tres turnos y sus totales

#### Scenario: Formato de exportación no soportado
- **GIVEN** una liquidación existente del consultorio
- **WHEN** se solicita la exportación con un formato distinto de `csv` o `json`
- **THEN** el sistema responde `422` y no genera archivo

### Requirement: Auditoría de las transiciones de la liquidación
Cada alta, edición de débitos, presentación, registro de resultado y anulación MUST registrar un evento append-only en `Auditoria` con actor, entidad, identificador y diferencia antes/después (`RN-SE-01`), sin datos personales del paciente (`R9`).

#### Scenario: La presentación deja rastro de auditoría
- **GIVEN** una liquidación `borrador` con turnos
- **WHEN** el usuario la presenta
- **THEN** se registra un evento con acción de presentación, actor y el cambio de estado `borrador → presentada`

#### Scenario: El débito deja rastro de auditoría
- **GIVEN** un borrador con un turno reclamado
- **WHEN** se registra un `monto_reconocido` con motivo de débito
- **THEN** se registra un evento con los montos antes y después del detalle, sin identificadores de paciente

### Requirement: Control de acceso a cobertura y liquidaciones
Consultar cobertura y liquidaciones MUST requerir rol Dueño, Recepción u Odontólogo. Crear, editar débitos, presentar, registrar resultado y anular MUST requerir rol Dueño o Recepción. Exportar MUST requerir rol Dueño o Recepción y MUST NOT concederse al Odontólogo (`03_actores_y_roles.md`, `R4`).

#### Scenario: El odontólogo no puede crear ni anular liquidaciones
- **GIVEN** un usuario autenticado con rol Odontólogo
- **WHEN** intenta crear o anular una liquidación
- **THEN** el sistema responde `403` sin revelar si la liquidación existe

#### Scenario: El odontólogo puede consultar la cobertura de un turno
- **GIVEN** un usuario autenticado con rol Odontólogo
- **WHEN** consulta la cobertura de una prestación de su consultorio
- **THEN** el sistema responde la cobertura y el monto a cargo

#### Scenario: Recepción exporta y el odontólogo no
- **GIVEN** una liquidación del consultorio y dos usuarios autenticados, uno de Recepción y otro Odontólogo
- **WHEN** ambos solicitan la exportación
- **THEN** Recepción obtiene el archivo y el Odontólogo recibe `403`
