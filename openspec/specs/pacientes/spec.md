# pacientes Specification

## Purpose
Permite gestionar el registro, búsqueda, deduplicación y consentimiento de comunicación de los pacientes del consultorio odontológico sin requerir inicio de sesión, vinculando a cada uno una ficha clínica única 1:1.

## Requirements

### Requirement: Unicidad de DNI por consultorio
El sistema SHALL garantizar que la combinación de `tenant_id` y `dni` sea única, permitiendo que un mismo DNI exista en diferentes consultorios pero impidiendo duplicados dentro del mismo consultorio.

#### Scenario: Creación con DNI nuevo en el consultorio
- **WHEN** un usuario con rol autorizado crea un paciente con un DNI no registrado previamente en su consultorio
- **THEN** el sistema registra el paciente exitosamente con código HTTP 201 y asigna un identificador único

#### Scenario: Rechazo por DNI duplicado en el mismo consultorio
- **WHEN** se intenta crear un paciente con un DNI que ya existe para el mismo `tenant_id`
- **THEN** el sistema rechaza la operación con código HTTP 409 Conflicto y un mensaje explicativo en español rioplatense

#### Scenario: Mismo DNI en consultorios distintos permitido
- **WHEN** se registra un paciente con un DNI idéntico al de otro paciente pero perteneciente a un `tenant_id` diferente
- **THEN** el sistema permite el registro exitosamente en ambos consultorios de forma independiente

### Requirement: Ficha clínica 1:1 inicializada con el paciente
El sistema SHALL crear automáticamente una ficha clínica vacía vinculada de forma 1:1 a cada nuevo paciente en el momento de su alta.

#### Scenario: Creación implícita de ficha clínica
- **WHEN** se da de alta un nuevo paciente en el sistema
- **THEN** se crea de forma atómica una entidad `FichaClinica` con `paciente_id` correspondiente y campos clínicos inicializados vacíos

#### Scenario: Detalle de paciente incluye su ficha clínica
- **WHEN** se consulta el detalle de un paciente existente vía `GET /api/pacientes/:id`
- **THEN** la respuesta incluye los datos del paciente y la información básica de su ficha clínica vinculada

### Requirement: Búsqueda y filtrado de pacientes
El sistema SHALL permitir listar y buscar pacientes filtrando por DNI, por número de teléfono o por término de búsqueda general sobre nombre, DNI y teléfono, restringiendo siempre los resultados al `tenant_id` del usuario autenticado.

#### Scenario: Búsqueda exacta por DNI
- **WHEN** el usuario consulta `GET /api/pacientes?dni=12345678`
- **THEN** el sistema devuelve una lista con el paciente que coincida exactamente con ese DNI dentro del consultorio

#### Scenario: Búsqueda por teléfono
- **WHEN** el usuario consulta `GET /api/pacientes?telefono=1122334455`
- **THEN** el sistema devuelve los pacientes cuyo teléfono coincida con el parámetro dentro del consultorio

#### Scenario: Aislamiento estricto de pacientes entre consultorios
- **WHEN** un usuario consulta o busca pacientes en `/api/pacientes`
- **THEN** el sistema devuelve únicamente pacientes pertenecientes a su propio `tenant_id`, nunca de otros consultorios

### Requirement: Consentimiento de WhatsApp (RN-CO-01) y baja STOP
El sistema SHALL almacenar el consentimiento de WhatsApp del paciente (`optin_wa`), estableciéndolo en `false` por defecto, bloqueando todo mensaje automático si no hay opt-in activo y cortando los envíos de forma inmediata si se procesa una baja (STOP).

#### Scenario: Bloqueo de mensaje automático sin opt-in
- **WHEN** se intenta despachar un mensaje automático a un paciente con `optin_wa = false`
- **THEN** el sistema bloquea el envío y registra la omisión de acuerdo con la regla RN-CO-01

#### Scenario: Actualización de opt-in a verdadero
- **WHEN** el usuario envía `PATCH /api/pacientes/:id/optin` con `optin_wa = true`
- **THEN** el sistema actualiza el estado del paciente y permite futuros envíos automáticos

#### Scenario: Baja STOP corta los envíos
- **WHEN** el paciente solicita la baja de mensajes y se procesa `PATCH /api/pacientes/:id/optin` con `optin_wa = false`
- **THEN** el sistema desactiva el consentimiento y los mensajes automáticos quedan inmediatamente bloqueados

### Requirement: Alta implícita en reserva con get_or_create por DNI
El sistema SHALL proveer la funcionalidad de `get_or_create` por DNI para el flujo de reserva pública: si el paciente con ese DNI ya existe en el consultorio, retorna el paciente existente actualizando sus datos de contacto si fueron provistos; si no existe, lo crea junto con su ficha clínica.

#### Scenario: Paciente existente en reserva pública
- **WHEN** se invoca `get_or_create` con el DNI de un paciente ya registrado en el consultorio
- **THEN** el sistema retorna la entidad del paciente existente y actualiza nombre o teléfono si difieren

#### Scenario: Paciente nuevo en reserva pública
- **WHEN** se invoca `get_or_create` con un DNI no registrado previamente en el consultorio
- **THEN** el sistema crea un nuevo paciente con su ficha clínica 1:1 y `optin_wa = false` por defecto

### Requirement: Baja lógica de pacientes (R7)
El sistema SHALL implementar la eliminación de pacientes mediante baja lógica (`activo = false`), prohibiendo el borrado físico (hard delete) para resguardar la trazabilidad clínica y legal.

#### Scenario: Borrado lógico de paciente
- **WHEN** un usuario autorizado ejecuta `DELETE /api/pacientes/:id`
- **THEN** el sistema establece `activo = false`, registra la acción en la tabla de auditoría y no elimina la fila física de la base de datos

### Requirement: Control de acceso RBAC sobre pacientes
El sistema SHALL restringir las operaciones sobre `/api/pacientes` según la matriz RBAC: los roles Dueño y Recepción tienen permisos CRUD completos, mientras que el rol Odontólogo posee permiso exclusivo de solo lectura.

#### Scenario: Odontólogo consulta pacientes
- **WHEN** un usuario con rol odontólogo ejecuta `GET /api/pacientes` o `GET /api/pacientes/:id`
- **THEN** el sistema permite la consulta con código HTTP 200

#### Scenario: Odontólogo intenta crear o modificar paciente
- **WHEN** un usuario con rol odontólogo intenta ejecutar `POST`, `PATCH` o `DELETE` sobre `/api/pacientes`
- **THEN** el sistema rechaza la solicitud con código HTTP 403 Prohibido

### Requirement: Exportación del paquete de datos del paciente (RN-SE-02)

El sistema MUST exponer `GET /api/pacientes/{paciente_id}/exportar-datos` para entregar un paquete JSON con los datos del paciente, generado en el servidor. La operación MUST requerir rol Dueño: Recepción y Odontólogo MUST recibir `403`. El paquete MUST incluir solo datos del paciente pedido y del tenant del token (`R4`, `R9`).

#### Scenario: Dueño exporta el paquete del paciente

- **WHEN** el Dueño solicita el paquete de un paciente de su consultorio
- **THEN** el sistema responde `200` con un JSON descargable que incluye identificación, contacto, turnos, ficha clínica, evoluciones, odontograma, presupuestos, consentimientos y movimientos de caja propios

#### Scenario: Recepción no exporta datos del paciente

- **WHEN** un usuario con rol `recepcion` solicita el paquete de datos de un paciente
- **THEN** el sistema responde `403` y no devuelve ningún dato del paciente

#### Scenario: Odontólogo no exporta datos del paciente

- **WHEN** un usuario con rol `odontologo` solicita el paquete de datos de un paciente
- **THEN** el sistema responde `403` y no devuelve ningún dato del paciente

#### Scenario: Paciente de otro consultorio no se exporta

- **GIVEN** un paciente del tenant B
- **WHEN** el Dueño del tenant A pide su paquete de datos
- **THEN** el sistema responde `404` con el mismo mensaje que para un paciente inexistente, sin revelar su existencia ni sus datos

### Requirement: Alcance mínimo y exclusiones del paquete de datos

El paquete MUST limitarse a los datos necesarios para responder el derecho de acceso: identificación y contacto, turnos, ficha clínica y evoluciones, odontograma, presupuestos con sus ítems, consentimientos (versión, hash de firma, fechas y canal) y movimientos de caja vinculados a sus turnos. MUST NOT incluir datos de otros pacientes, el trail de auditoría, credenciales, tokens, el contenido binario de adjuntos clínicos ni el **nombre de archivo** de esos adjuntos.

#### Scenario: El paquete incluye las secciones comprometidas

- **GIVEN** un paciente con turnos, ficha, evolución, evento de odontograma, presupuesto, consentimiento y un cobro vinculado
- **WHEN** el Dueño descarga su paquete
- **THEN** el JSON contiene cada una de esas secciones con los registros del paciente y sus totales calculados en el servidor (`R8`)

#### Scenario: El paquete no incluye datos de terceros ni secretos

- **GIVEN** un paciente del tenant A y otros pacientes del mismo consultorio, con eventos de auditoría y adjuntos clínicos
- **WHEN** el Dueño descarga el paquete del paciente
- **THEN** el JSON no contiene datos de los otros pacientes, ni registros de auditoría, ni tokens, ni el contenido binario de los adjuntos, y solo incluye la metadata de los adjuntos del paciente

#### Scenario: Los adjuntos van sin nombre de archivo

- **GIVEN** un paciente con un adjunto cuyo nombre original es `radiografia-juan-perez.jpg`
- **WHEN** el Dueño descarga el paquete
- **THEN** la sección `adjuntos` informa la cantidad y, por cada adjunto, tipo, `mime_type`, tamaño y fecha, sin el nombre del archivo ni parte de él

#### Scenario: El consentimiento incluye el hash de firma

- **GIVEN** un paciente con un consentimiento firmado
- **WHEN** el Dueño descarga el paquete
- **THEN** la sección `consentimientos` incluye `texto_version`, `firma_hash`, `firmado_at`, `canal` y `revocado`, y no incluye el texto completo del consentimiento

#### Scenario: Paciente sin actividad recibe el paquete vacío

- **GIVEN** un paciente existente del tenant sin turnos, ficha, evoluciones, consentimientos ni presupuestos
- **WHEN** el Dueño pide su paquete de datos
- **THEN** el sistema responde `200` con las listas vacías y `ficha_clinica: null`, sin `404` ni error

#### Scenario: Un paciente con prestación invasiva sin consentimiento se exporta igual

- **GIVEN** un paciente atendido con una prestación invasiva que no tiene consentimiento firmado
- **WHEN** el Dueño pide su paquete de datos
- **THEN** el sistema responde `200` con los datos disponibles y `consentimientos: []`, porque `RN-CL-02` gatea la atención, no el derecho de acceso

### Requirement: Protección contra IDOR y registro del pedido de exportación

La exportación MUST identificar al paciente por UUID del servidor, resolverlo siempre dentro del tenant del token y responder `404` uniforme para inexistente o ajeno, sin habilitar enumeración por DNI ni por nombre. Cada pedido MUST quedar registrado en `auditoria` con paciente, formato y secciones, sin PHI en el evento, en logs ni en URLs (`R9`, `RN-SE-01`).

#### Scenario: UUID inexistente y UUID ajeno responden igual

- **WHEN** el Dueño del tenant A pide el paquete con un UUID inexistente y con el UUID de un paciente del tenant B
- **THEN** ambas respuestas son `404` con el mismo mensaje y el mismo cuerpo

#### Scenario: Identificador malformado se rechaza antes de consultar

- **WHEN** el Dueño pide el paquete con un identificador que no es un UUID
- **THEN** el sistema responde `422` sin consultar la base ni revelar datos

#### Scenario: La exportación del paciente deja evento sin PHI

- **WHEN** el Dueño descarga el paquete de datos de un paciente
- **THEN** queda un evento `paciente.exportar_datos` con el identificador del paciente, el formato y las secciones incluidas, sin DNI, teléfono, nombre ni contenido clínico

### Requirement: Fallo de auditoría y nombre de archivo del paquete

Si la inserción del evento `paciente.exportar_datos` falla, el sistema MUST NOT entregar el paquete y MUST responder `500` o `503` con un mensaje genérico. La descarga MUST incluir `Content-Disposition` y `Cache-Control: no-store`, con un nombre de archivo opaco (UUID del paciente y fecha), sin DNI ni nombre.

#### Scenario: Si falla la auditoría no se entrega el paquete

- **GIVEN** una falla al insertar el evento de auditoría del paquete
- **WHEN** el Dueño pide el paquete de un paciente
- **THEN** el sistema responde `500` o `503` con un mensaje genérico y no devuelve ningún JSON

#### Scenario: El nombre del archivo del paquete es opaco

- **WHEN** el Dueño descarga el paquete de un paciente
- **THEN** el nombre del archivo contiene solo un identificador opaco y la fecha, sin DNI, nombre ni teléfono, y la respuesta es `no-store`
