# frontend-caja-os Specification

## Purpose

Proporciona las pantallas internas del dinero y la facturación del consultorio sobre el shell autenticado: caja diaria con movimientos y cierre, cobro del saldo de la atención, señas, consulta de cobertura de obra social, liquidaciones con débitos y exportación generada en el servidor, respetando que los montos los calcula siempre el backend y que un cierre cerrado es inmutable.

## Requirements

### Requirement: Movimientos de caja

El sistema SHALL listar y registrar movimientos de caja (ingreso/egreso) por medio de pago, mostrando siempre el monto informado por el servidor.

#### Scenario: Listado con filtros
- **WHEN** el usuario abre la caja de una fecha y filtra por medio de pago o tipo de movimiento
- **THEN** el sistema consulta `/api/caja/movimientos` con esos filtros y muestra concepto, tipo, medio, monto, cierre asociado y quién lo registró.

#### Scenario: Alta de ingreso
- **WHEN** el usuario registra un ingreso con concepto, medio y monto
- **THEN** el sistema envía `POST /api/caja/movimientos`, recibe `201` y agrega el movimiento al listado con el monto que devolvió el servidor.

#### Scenario: Alta de egreso
- **WHEN** el usuario registra un egreso
- **THEN** el sistema lo envía con `tipo: "egreso"` y lo muestra restándolo del cierre abierto vigente, sin recalcular el total en el cliente.

#### Scenario: Datos inválidos
- **WHEN** falta el concepto o el monto es cero o negativo
- **THEN** el sistema muestra la validación local y no llama a la API.

#### Scenario: Sin cierre abierto
- **WHEN** no hay un cierre de caja abierto en el consultorio
- **THEN** el sistema permite registrar el movimiento pero advierte que, sin cierre abierto, ese movimiento no va a entrar en el cierre del día (RN-PA-05).

### Requirement: Apertura y cierre de caja diario

El sistema SHALL permitir abrir el cierre de una fecha y cerrarlo informando el total contado, mostrando la diferencia calculada por el servidor con signo y sin cerrar en silencio un descuadre.

#### Scenario: Apertura del día
- **WHEN** el usuario abre el cierre de una fecha
- **THEN** el sistema envía `POST /api/caja/cierre` y muestra el cierre en estado `abierto` con la fecha y quién lo abrió.

#### Scenario: Fecha ya abierta
- **WHEN** ya existe un cierre para esa fecha
- **THEN** el sistema muestra el `409` del backend, abre el cierre existente en vez de crear otro y no duplica la apertura.

#### Scenario: Cierre con total contado
- **WHEN** el usuario cierra la caja ingresando el total contado
- **THEN** el sistema envía `POST /api/caja/cierre/{id}/cerrar`, recibe `200` y muestra `total_sistema`, `total_contado` y `diferencia` tal como los devolvió el servidor.

#### Scenario: Diferencia distinta de cero
- **WHEN** el total contado no coincide con el total del sistema (la diferencia es distinta de cero)
- **THEN** el sistema pide confirmación explícita antes de enviar el cierre, indicando si la diferencia es sobrante o faltante y el monto exacto (RN-PA-05).

#### Scenario: Monto contado inválido
- **WHEN** el total contado está vacío o es negativo
- **THEN** el sistema muestra la validación local y no envía el cierre.

### Requirement: Cierre cerrado inmutable y reapertura del Dueño

El sistema SHALL tratar un cierre cerrado como inmutable y SHALL ofrecer la reapertura únicamente al rol Dueño, exigiéndole un motivo.

#### Scenario: Cierre cerrado
- **WHEN** el usuario abre un cierre en estado `cerrado`
- **THEN** el sistema lo muestra como inmutable, sin acciones de edición ni de cierre, con la fecha de cierre y quién lo cerró.

#### Scenario: Reapertura por Dueño
- **WHEN** un usuario con rol `dueno` reabre un cierre indicando un motivo
- **THEN** el sistema envía `POST /api/caja/cierre/{id}/reabrir`, recibe `200` y muestra el cierre en estado `abierto` con el motivo registrado.

#### Scenario: Reapertura sin motivo
- **WHEN** el usuario intenta reabrir sin escribir el motivo
- **THEN** el sistema no envía la reapertura y pide el motivo, explicando que queda auditado.

#### Scenario: Recepción intenta reabrir
- **WHEN** un usuario con rol `recepcion` no ve la acción de reabrir y fuerza el pedido
- **THEN** el sistema muestra el `403` del backend con el mensaje de permiso denegado y deja el cierre en estado `cerrado` (matriz §03: Recepción cierra pero no reabre).

### Requirement: Cobro del saldo de la atención

El sistema SHALL mostrar el saldo de una atención calculado por el servidor y SHALL registrar el cobro con el medio de pago elegido.

#### Scenario: Ver la liquidación del turno
- **WHEN** el usuario abre el cobro de un turno
- **THEN** el sistema consulta `GET /api/caja/turnos/{id}/liquidacion` y muestra precio particular, cobertura de obra social, seña ya cobrada y saldo, sin calcular ninguno de esos montos en el cliente (R8).

#### Scenario: Cobro exitoso
- **WHEN** el usuario cobra el saldo con un medio de pago
- **THEN** el sistema envía `POST /api/caja/turnos/{id}/cobrar`, recibe `201` y muestra el movimiento generado y la atención como saldada.

#### Scenario: Sin saldo pendiente
- **WHEN** el saldo de la atención es cero
- **THEN** el sistema deshabilita la acción de cobro y explica que la atención ya está saldada, sin enviar el pedido.

#### Scenario: Cobro rechazado
- **WHEN** la API rechaza el cobro (`409` o `422`)
- **THEN** el sistema muestra el motivo del backend y mantiene los montos de la última lectura del servidor, sin modificarlos localmente.

### Requirement: Gestión de señas

El sistema SHALL listar las señas del consultorio por estado y SHALL permitir cobrarlas, resolver su cancelación y marcarlas vencidas según el ciclo de vida de la seña.

#### Scenario: Listado por estado
- **WHEN** el usuario abre las señas filtrando por estado
- **THEN** el sistema consulta `/api/senas` con ese filtro y muestra monto, estado, turno asociado y vencimiento.

#### Scenario: Cobro de una seña
- **WHEN** el usuario cobra una seña `pendiente` indicando el medio
- **THEN** el sistema envía `POST /api/senas/{id}/cobrar`, recibe `200` y muestra la seña como `cobrada`.

#### Scenario: Cancelación por ausencia
- **WHEN** el usuario resuelve la cancelación de una seña marcando al paciente como ausente
- **THEN** el sistema envía la resolución con `ausente: true` y muestra el estado resultante que devuelve el servidor, que retiene la seña cobrada y la aplica a gastos (RN-PA-04).

#### Scenario: Seña vencida
- **WHEN** el usuario marca una seña `pendiente` como vencida
- **THEN** el sistema envía el vencimiento, recibe `200` y muestra la seña en estado `vencida` sin habilitar su cobro posterior.

#### Scenario: Acción no válida para el estado
- **WHEN** la seña no está en un estado que admita la acción elegida
- **THEN** el sistema no ofrece la acción en la interfaz y, si el backend la rechaza, muestra el motivo sin cambiar el estado local.

### Requirement: Cobertura de obra social al agendar

El sistema SHALL consultar la cobertura vigente de una prestación para una obra social y SHALL mostrar el monto a cargo informado por el servidor, incluyendo la advertencia de arancel vencido.

#### Scenario: Cobertura vigente
- **WHEN** el usuario consulta la cobertura de una prestación para una obra social con padrón vigente
- **THEN** el sistema llama a `GET /api/os/cobertura` y muestra precio particular, cobertura y monto a cargo devueltos por el servidor (US-040, RN-OS-01).

#### Scenario: Sin cobertura
- **WHEN** la obra social no tiene cobertura para esa prestación
- **THEN** el sistema muestra el monto a cargo igual al precio particular y aclara que se factura como particular (RN-OS-01).

#### Scenario: Arancel vencido
- **WHEN** la respuesta trae `arancel_vencido: true` con una advertencia
- **THEN** el sistema muestra la advertencia tal como la redactó el servidor, sin bloquear la consulta ni corregir el monto.

#### Scenario: Consulta fallida
- **WHEN** la consulta de cobertura falla por red o `5xx`
- **THEN** el sistema avisa que no pudo verificar la cobertura y no inventa un monto, dejando que la operación siga sin cobertura confirmada.

### Requirement: Liquidaciones por obra social y período

El sistema SHALL permitir crear liquidaciones por obra social y período, y SHALL mostrar su estado y sus totales tal como los devuelve el servidor.

#### Scenario: Alta de liquidación
- **WHEN** el usuario crea una liquidación indicando obra social y período
- **THEN** el sistema envía `POST /api/liquidaciones`, recibe `201` y muestra la liquidación en estado `borrador` con el total calculado por el servidor.

#### Scenario: Liquidación abierta duplicada
- **WHEN** ya existe una liquidación abierta para esa obra social y período
- **THEN** el sistema muestra el `409` del backend y ofrece abrir la liquidación existente en lugar de crear otra (RN-OS-02).

#### Scenario: Período con formato inválido
- **WHEN** el período no cumple el formato esperado
- **THEN** el sistema muestra la validación local y no llama a la API.

#### Scenario: Sin turnos liquidables
- **WHEN** la obra social y el período no tienen turnos finalizados
- **THEN** el sistema muestra un estado vacío que explica que solo los turnos `finalizado` entran en liquidación (RN-OS-02).

### Requirement: Débitos y cierre de la liquidación

El sistema SHALL permitir cerrar una liquidación y registrar débitos por turno con motivo, informando los turnos sin cobertura y las advertencias del servidor.

#### Scenario: Cierre de liquidación
- **WHEN** el usuario cierra una liquidación en borrador
- **THEN** el sistema envía `POST /api/liquidaciones/{id}/cerrar`, recibe `200` y muestra la liquidación en estado `presentada` con sus totales definitivos.

#### Scenario: Débito sin motivo
- **WHEN** el usuario registra un débito sin escribir el motivo
- **THEN** el sistema muestra la validación y no envía el débito, porque todo débito exige motivo (US-041 CA-1).

#### Scenario: Resultado con débitos
- **WHEN** el usuario registra el resultado como `con_debitos` con sus detalles y motivos
- **THEN** el sistema envía `POST /api/liquidaciones/{id}/resultado`, recibe `200` y muestra el estado `con_debitos`, el total reconocido y el detalle por turno.

#### Scenario: Turnos sin cobertura
- **WHEN** la liquidación informa `turnos_sin_cobertura` mayor que cero o advertencias
- **THEN** el sistema las muestra de forma destacada antes de cerrar, sin modificar los montos del servidor.

### Requirement: Anulación de liquidación

El sistema SHALL permitir anular una liquidación únicamente con motivo y SHALL impedir operar sobre una liquidación anulada.

#### Scenario: Anulación con motivo
- **WHEN** el usuario anula una liquidación indicando el motivo
- **THEN** el sistema envía la anulación, recibe `200` y muestra la liquidación en estado `anulada` con el motivo visible.

#### Scenario: Anulación sin motivo
- **WHEN** el usuario intenta anular sin escribir el motivo
- **THEN** el sistema no envía la anulación y pide el motivo.

#### Scenario: Liquidación anulada
- **WHEN** el usuario abre una liquidación `anulada`
- **THEN** el sistema la muestra en solo lectura, sin acciones de cierre, resultado ni exportación.

### Requirement: Exportación de liquidaciones

El sistema SHALL descargar la exportación de una liquidación generada por el servidor en CSV o JSON, sin armarla en el cliente.

#### Scenario: Exportación CSV
- **WHEN** el usuario exporta una liquidación en CSV
- **THEN** el sistema descarga el archivo que devuelve `GET /api/liquidaciones/{id}/exportar?formato=csv`, usando el nombre de archivo que indique la respuesta.

#### Scenario: Exportación JSON
- **WHEN** el usuario exporta la misma liquidación en JSON
- **THEN** el sistema descarga el archivo JSON del servidor y no reutiliza el CSV ya descargado.

#### Scenario: Exportación rechazada
- **WHEN** la exportación responde `403`, `404` o `5xx`
- **THEN** el sistema muestra el error y no genera ningún archivo vacío ni deja una descarga a medias.

#### Scenario: Odontólogo no exporta liquidaciones
- **WHEN** un usuario con rol `odontologo` abre una liquidación
- **THEN** el sistema la muestra en solo lectura y no ofrece la acción de exportar, porque §03 le da lectura sin exportación sobre liquidaciones OS.

### Requirement: Alcance por rol en caja y obras sociales

El sistema SHALL habilitar acciones de caja y obras sociales según la matriz de permisos del backend, manteniendo al servidor como autoridad final.

#### Scenario: Odontólogo en caja
- **WHEN** un usuario con rol `odontologo` abre la caja
- **THEN** el sistema le muestra los movimientos en solo lectura y no ofrece alta de movimientos, apertura ni cierre de caja.

#### Scenario: Recepción en caja
- **WHEN** un usuario con rol `recepcion` opera la caja
- **THEN** el sistema le permite movimientos, apertura, cierre, cobros y señas, pero no la reapertura de un cierre.

#### Scenario: Acción rechazada por el backend
- **WHEN** una acción visible obtiene `403` de la API
- **THEN** el sistema muestra el mensaje de permiso denegado del backend, refresca la identidad y no reintenta la acción.

#### Scenario: Exportación parcial por rol
- **WHEN** un usuario con rol `recepcion` exporta una liquidación
- **THEN** el sistema permite la descarga, porque §03 le da liquidaciones de obras sociales con exportación.
