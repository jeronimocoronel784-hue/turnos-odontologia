# Spec Delta

## Purpose

Proveer la gestión multi-tenant de la agenda odontológica, incluyendo la máquina de estados del turno, el control anti-solapamiento por profesional y sillón con sugerencia de horarios alternativos, los bloqueos horarios, la reprogramación con trazabilidad y los flujos públicos de reserva y autogestión por token opaco.

## ADDED Requirements

### Requirement: Máquina de estados cerrada del turno
The system SHALL enforce a closed state graph for appointments (`pendiente → confirmado → presente → finalizado`, plus branches from `pendiente` or `confirmado` to `cancelado`, `ausente`, or `reprogramado`), rejecting any out-of-graph transition and writing every transition to the append-only audit log (RN-AG-07, RN-SE-01).

#### Scenario: Transición válida de pendiente a confirmado y presente a finalizado
- **WHEN** un operador autorizado confirma un turno en estado `pendiente`, luego lo marca `presente` y finalmente `finalizado`
- **THEN** cada transición se persiste con éxito y genera una entrada inmutable en la tabla `auditoria`

#### Scenario: Rechazo de transición fuera del grafo
- **WHEN** se intenta pasar un turno de `finalizado` o `cancelado` a `confirmado`, o de `pendiente` directamente a `finalizado`
- **THEN** el sistema MUST rechazar la operación con `422 Unprocessable Entity` y un mensaje claro en español rioplatense

### Requirement: Cálculo de duración por prestación y sobreturno explícito
The system SHALL compute `fin = inicio + duracion_min` from the selected service unless an explicit override is audited (RN-AG-02), and MUST require an explicit `sobreturno = true` flag with a non-empty reason to allow an overbooking (RN-AG-04).

#### Scenario: Cálculo automático de fin según duración de la prestación
- **WHEN** se agenda un turno a las `10:00` para una prestación con `duracion_min = 45` sin especificar `fin`
- **THEN** el sistema persiste el turno con `fin = 10:45`

#### Scenario: Rechazo de sobreturno sin motivo
- **WHEN** se envía una solicitud de turno con `sobreturno = true` y sin motivo u observaciones
- **THEN** el sistema MUST rechazar la solicitud con `422 Unprocessable Entity` exigiendo el motivo del sobreturno

### Requirement: Anti-solapamiento por profesional y sillón con alternativas
The system SHALL prevent overlapping active appointments (`pendiente`, `confirmado`, `presente`) in the `[inicio, fin)` range for the same professional or chair unless `sobreturno = true` (RN-AG-01), returning `409 Conflict` with alternative available slots and a Rioplatense Spanish message (RN-GL-02).

#### Scenario: Rechazo por solapamiento de profesional o sillón con sugerencia de slots
- **WHEN** se intenta agendar un turno normal que se superpone en rango `[inicio, fin)` con otro turno activo del mismo profesional o del mismo sillón
- **THEN** el sistema MUST responder `409 Conflict` incluyendo mensaje en rioplatense y una lista de horarios alternativos disponibles cercanos

#### Scenario: Admisión de solapamiento cuando es sobreturno explícito
- **WHEN** recepción o dueño crea un turno con `sobreturno = true` y motivo explícito en un horario ya ocupado por otro turno del profesional
- **THEN** el sistema permite crear el turno marcado como sobreturno y registra el evento en auditoría

### Requirement: Bloqueos horarios no reservables
The system SHALL allow creating time blocks (`Bloqueo`) for a professional, a chair, or both with a reason (`feriado`, `vacaciones`, `manual`, `administrativo`), and MUST reject any appointment or public booking that overlaps an active block (RN-AG-03).

#### Scenario: Intento de agendar sobre un rango bloqueado
- **WHEN** se intenta crear un turno (incluso con `sobreturno = true` o por reserva pública) dentro del rango `[desde, hasta)` de un bloqueo del profesional o del sillón
- **THEN** el sistema MUST rechazar la reserva con `409 Conflict` e informar horarios alternativos libres

#### Scenario: Alta de bloqueo sin profesional ni sillón rechazada
- **WHEN** se intenta crear un bloqueo con `profesional_id = null` y `sillon_id = null` o con `hasta <= desde`
- **THEN** el sistema MUST rechazar la solicitud con `422 Unprocessable Entity`

### Requirement: Reprogramación en 1 clic con trazabilidad histórica
The system SHALL reprogram an appointment by transitioning the original appointment to `reprogramado` and creating a new appointment linked via `turno_origen_id`, without mutating the original appointment's times (RN-AG-06).

#### Scenario: Reprogramación exitosa preserva turno original y vincula el nuevo
- **WHEN** se reprograma un turno `pendiente` o `confirmado` hacia un nuevo horario libre
- **THEN** el turno original queda en estado `reprogramado` con su horario original intacto y se crea un nuevo turno en `pendiente` con `turno_origen_id` apuntando al original

#### Scenario: Reprogramación fuera de término por canal público
- **WHEN** un paciente intenta cancelar o reprogramar su turno por token público faltando menos horas que la política `cancelacion_hs` del consultorio
- **THEN** el sistema MUST rechazar la operación automática por fuera de término con `409 Conflict` y mensaje explicativo en español rioplatense (RN-AG-05)

### Requirement: Vista de agenda multi-profesional y control RBAC
The system SHALL expose `GET /api/agenda` to query appointments and blocks by date range, professional, and chair, enforcing RBAC permissions on `Recurso.AGENDA` and `Recurso.BLOQUEOS` and isolating data strictly by the JWT `tenant_id` (R4).

#### Scenario: Consulta de agenda diaria o semanal con turnos y bloqueos del consultorio
- **WHEN** un usuario autenticado consulta `GET /api/agenda?desde=...&hasta=...`
- **THEN** recibe únicamente los turnos y bloqueos de su `tenant_id` en ese rango, y ningún dato de otro consultorio

#### Scenario: Odontólogo actualiza estado de su turno pero no crea bloqueos
- **WHEN** un usuario con rol `odontologo` cambia el estado de un turno a `presente` o `finalizado` pero intenta crear un bloqueo administrativo en `POST /api/bloqueos`
- **THEN** el cambio de estado del turno es aceptado (`200 OK`) y la creación del bloqueo es rechazada con `403 Forbidden`

### Requirement: Reserva pública 24/7 y autogestión por token opaco
The system SHALL expose public endpoints `GET/POST /reservar/{slug}` and `/mis-turnos/{token}` allowing a patient without an account to query real available slots, book an appointment (creating or updating the patient by DNI and issuing an opaque `TokenGestion`), and view, confirm, cancel, or reschedule ONLY that appointment (RN-SE-03, RN-PA-01).

#### Scenario: Reserva online crea paciente, turno pendiente y token de gestión
- **WHEN** un paciente envía `POST /reservar/{slug}` con nombre, DNI, teléfono, prestación, profesional, sillón e inicio disponible
- **THEN** el sistema registra o actualiza al paciente, crea el turno en estado `pendiente`, indica si requiere seña (`requiere_sena`, `monto_sena`) y devuelve el `token_gestion` en claro por única vez

#### Scenario: Bloqueo de confirmación cuando la prestación exige seña impaga
- **WHEN** se intenta pasar a `confirmado` un turno cuya prestación tiene `requiere_sena = true` sin que la seña haya sido acreditada
- **THEN** el sistema MUST rechazar la confirmación con `409 Conflict` indicando que la seña exigible sigue pendiente de pago (RN-PA-01)

#### Scenario: Token público de un turno no permite gestionar otro turno ni otro tenant
- **WHEN** alguien invoca `/mis-turnos/{token}` con un token vencido, inexistente o perteneciente a otro recurso
- **THEN** el sistema MUST responder `401 Unauthorized` sin exponer datos de terceros (RN-SE-03)
