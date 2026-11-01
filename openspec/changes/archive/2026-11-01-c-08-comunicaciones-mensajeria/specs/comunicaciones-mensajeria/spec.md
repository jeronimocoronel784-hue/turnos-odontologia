# Spec: Comunicaciones y Mensajería (`comunicaciones-mensajeria`)

## ADDED Requirements

### Requirement: Outbox idempotente y plantillas versionadas
El sistema MUST persistir cada envío automático en la tabla outbox `mensaje` con un `idempotency_key` único por `tenant_id` (`RN-CO-02`) y asociarlo a la versión exacta de la `plantilla` utilizada y al texto renderizado (`RN-CO-04`). Un mismo `(turno, plantilla, ventana)` MUST generar un único registro en el outbox aunque se invoque múltiples veces.

#### Scenario: Encolar dos veces el mismo recordatorio 24h no duplica el mensaje
- **GIVEN** un turno activo y la plantilla `recordatorio_24h` versión 1
- **WHEN** se solicita programar el recordatorio 24h dos veces con la misma ventana
- **THEN** el sistema conserva un único registro en `mensaje` con el mismo `idempotency_key` y versión de plantilla.

### Requirement: Respeto estricto de opt-in WhatsApp y reintentos con backoff
Antes de despachar un mensaje de canal `wa`, el procesador de outbox MUST verificar que el paciente tenga `optin_wa = True` (`RN-CO-01`). Si `optin_wa = False`, el sistema MUST NOT enviar el mensaje por WhatsApp y MUST registrar la omisión con motivo auditable (`omitido`) o derivar a email si corresponde. Ante fallos del proveedor de transporte, el sistema MUST incrementar `intentos` y reprogramar el envío con backoff sin duplicar el registro (`RN-CO-03`).

#### Scenario: Paciente sin opt-in WA no recibe WhatsApp y queda registrado como omitido
- **GIVEN** un paciente con `optin_wa = False` y un mensaje `pendiente` en canal `wa`
- **WHEN** el worker procesa el outbox
- **THEN** no se invoca el envío de WhatsApp y el mensaje pasa a estado `omitido` con el motivo registrado.

#### Scenario: Fallo transitorio del proveedor reprograma reintento sin duplicar fila
- **GIVEN** un mensaje `pendiente` con `optin_wa = True` y `intentos = 0`
- **WHEN** el proveedor falla en el primer intento
- **THEN** el mismo registro incrementa `intentos = 1`, reprograma `programado_para` hacia el futuro con backoff y permanece `pendiente` (o pasa a `fallido` al alcanzar `max_intentos`).

### Requirement: Webhook de WhatsApp con firma HMAC, confirmación idempotente y baja STOP
El endpoint `POST /webhooks/whatsapp` MUST validar la firma HMAC-SHA256 (`X-Hub-Signature-256`) antes de procesar cualquier evento (`R8`, `RN-SE-04`). Un evento de confirmación de turno MUST pasar el turno a `confirmado` de forma idempotente (`RN-AG-08`). Un mensaje entrante `STOP` (o `BAJA`) MUST actualizar `optin_wa = False` en el paciente correspondiente y registrar auditoría (`RN-CO-01`).

#### Scenario: Firma HMAC inválida es rechazada con 401
- **GIVEN** un payload de webhook de WhatsApp con cabecera `X-Hub-Signature-256` inválida o ausente
- **WHEN** se envía `POST /webhooks/whatsapp`
- **THEN** el sistema responde `401 Unauthorized` sin modificar turnos ni pacientes.

#### Scenario: Webhook de confirmación repetido confirma una sola vez y STOP revoca opt-in
- **GIVEN** un webhook válido con acción de confirmar un turno `pendiente`
- **WHEN** se recibe dos veces el mismo evento
- **THEN** el turno queda en `confirmado` con una única transición efectiva
- **AND** cuando llega un evento válido con texto `STOP` del teléfono del paciente, `optin_wa` pasa a `False`.

### Requirement: Control de acceso RBAC en endpoints de mensajería
Los endpoints internos `/api/mensajes*` y `/api/plantillas*` MUST exigir JWT válido, aislar por `tenant_id` (`R4`) y aplicar la matriz RBAC para `Recurso.MENSAJES`: `dueno` posee CRUD completo, `recepcion` posee `LEER` y `REENVIAR`, y `odontologo` no posee acceso (`403 Forbidden`).

#### Scenario: Odontólogo recibe 403 en mensajería y Recepción puede listar y reenviar
- **GIVEN** usuarios autenticados con roles `odontologo` y `recepcion`
- **WHEN** `odontologo` consulta `GET /api/mensajes` y `recepcion` invoca `GET /api/mensajes` y `POST /api/mensajes/{id}/reenviar`
- **THEN** `odontologo` recibe `403 Forbidden` y `recepcion` recibe `200 OK`.
