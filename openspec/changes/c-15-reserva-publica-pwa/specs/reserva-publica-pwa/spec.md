# Spec Delta

## Purpose
Proporciona una aplicación web progresiva (PWA) móvil-first para que los pacientes reserven citas online 24/7, gestionen sus turnos existentes por token opaco, paguen señas y firmen consentimientos informados de forma offline-resiliente.

## ADDED Requirements

### Requirement: Catálogo y selección de turnos online
El sistema SHALL permitir al paciente consultar las prestaciones activas de un consultorio, filtrar por profesional o sillón y visualizar las franjas horarias disponibles en tiempo real.

#### Scenario: Carga exitosa del catálogo y slots
- **WHEN** el paciente ingresa a `/reservar/:slug`
- **THEN** el sistema consulta `/api/reservar/:slug` y renderiza el listado de prestaciones, odontólogos, sillones y los horarios libres sin solapamientos.

#### Scenario: Consultorio no encontrado o inactivo
- **WHEN** el paciente accede a un slug inexistente o inactivo
- **THEN** el sistema muestra un mensaje claro en rioplatense indicando que el consultorio no fue encontrado.

### Requirement: Registro de reserva y paciente sin login
El sistema SHALL validar los datos del paciente (nombre completo, DNI argentino, teléfono móvil, email opcional, fecha de nacimiento y obra social) y requerir consentimiento opt-in para recordatorios de WhatsApp antes de registrar la cita.

#### Scenario: Envío exitoso del formulario de reserva
- **WHEN** el paciente selecciona un slot disponible, completa el formulario con datos válidos y envía la solicitud
- **THEN** el sistema realiza un `POST /api/reservar/:slug`, recibe el `token_gestion` y transiciona a la pantalla de confirmación o pago de seña.

#### Scenario: Conflicto de horario tomado concurrentemente
- **WHEN** el slot seleccionado fue reservado por otro usuario segundos antes (código 409)
- **THEN** el sistema muestra un mensaje amigable indicando que el horario acaba de ocuparse y ofrece franjas alternativas inmediatas.

### Requirement: Gestión de seña y pago online
El sistema SHALL detectar si la prestación requiere seña (`requiere_sena=true`) y guiar al paciente hacia el pago por Mercado Pago utilizando montos e identificadores provistos exclusivamente por el servidor.

#### Scenario: Prestación con seña obligatoria
- **WHEN** el turno creado requiere seña
- **THEN** el sistema muestra el monto exacto devuelto por la API, genera el enlace hacia `/pagar/:token` y proporciona el botón de pago seguro de Mercado Pago.

### Requirement: Autogestión de turno por token opaco
El sistema SHALL permitir al paciente visualizar los detalles de su turno, confirmarlo, reprogramarlo o cancelarlo a través de la ruta `/mis-turnos/:token` sin requerir usuario ni contraseña.

#### Scenario: Confirmación de cita
- **WHEN** el paciente accede a `/mis-turnos/:token` y presiona "Confirmar turno"
- **THEN** el sistema envía `POST /api/mis-turnos/:token/confirmar` y actualiza el estado a `confirmado`.

#### Scenario: Cancelación dentro del plazo permitido
- **WHEN** el paciente solicita cancelar su cita respetando la política de anticipación mínima del consultorio
- **THEN** el sistema procesa la cancelación, libera el horario en la agenda y confirma la acción al paciente.

### Requirement: Firma digital de consentimiento informado
El sistema SHALL presentar el texto del consentimiento informado en `/firmar/:token` y capturar la firma del paciente mediante trazo táctil/puntero o confirmación digital vinculada al hash SHA-256.

#### Scenario: Registro de consentimiento firmado
- **WHEN** el paciente revisa el consentimiento y estampa su firma digital
- **THEN** el sistema envía la firma a la API, asocia el hash inmutable a la historia clínica y muestra el comprobante.

### Requirement: Shell offline y resiliencia PWA
El sistema SHALL registrar un Service Worker que almacene en caché el shell de la aplicación para apertura instantánea sin conexión, manejando estados de red inestable sin almacenar datos médicos en `localStorage`.

#### Scenario: Apertura de la aplicación sin internet
- **WHEN** el paciente abre la PWA sin conectividad a internet
- **THEN** la aplicación carga su estructura visual y muestra un aviso contextual en rioplatense indicando que se encuentra en modo sin conexión.
