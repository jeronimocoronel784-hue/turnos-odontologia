# Spec Delta: `pacientes`

## ADDED Requirements

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
