# mercadopago-webhooks Specification

## Purpose
Procesar cobros y señas vía Mercado Pago con creación de preferencias con vencimiento, verificación criptográfica de webhooks con firma HMAC, procesamiento idempotente por identificador único de pago y conciliación con detección de discrepancias (`RN-PA-02`, `RN-PA-03`, `RN-PA-05`, `RN-SE-04`).

## Requirements

### Requirement: Creación de preferencia de pago vinculada a la seña con vencimiento estricto
El sistema MUST generar una preferencia en Mercado Pago para una `Sena` en estado `pendiente`, vinculando `external_reference` con el identificador de la seña y definiendo `expiration_date_to` coincidente con `sena.vence_at` (`RN-PA-02`). La preferencia MUST retornar la URL de inicio de checkout y su identificador para ser presentados al paciente o enviados por mensajería.

#### Scenario: Generación exitosa de link de pago con expiración sincronizada
- **GIVEN** una seña en estado `pendiente` con monto de `10000.00` y vencimiento dentro de 24 horas
- **WHEN** el servicio solicita la creación de preferencia para el paciente
- **THEN** el sistema genera la preferencia en Mercado Pago con `external_reference` igual al ID de la seña, `expiration_date_to` fijado y devuelve el link de pago seguro.

### Requirement: Verificación de firma criptográfica y persistencia cruda de webhooks de Mercado Pago
El sistema MUST verificar la cabecera `x-signature` del webhook de Mercado Pago mediante HMAC-SHA256 utilizando el secreto configurado del tenant (`RN-SE-04`). Todo webhook con firma válida MUST persistirse íntegramente en la tabla `cobro_mp` (`payload jsonb`) antes de desencadenar cualquier mutación en el dominio. Una firma inválida MUST ser rechazada con código `401 Unauthorized`.

#### Scenario: Webhook con firma válida es persistido en crudo
- **GIVEN** una notificación HTTP de Mercado Pago con encabezado `x-signature` válido para el tenant
- **WHEN** el endpoint `POST /webhooks/mercadopago` recibe el payload
- **THEN** el sistema valida la firma criptográfica, almacena el registro en `cobro_mp` con el payload JSONB y responde `200 OK`.

#### Scenario: Webhook con firma alterada o inválida es rechazado
- **GIVEN** una notificación HTTP con firma HMAC no correspondiente al secreto del tenant
- **WHEN** el endpoint de webhooks intenta procesarla
- **THEN** el sistema rechaza la petición con `401 Unauthorized` sin alterar datos del consultorio.

### Requirement: Procesamiento idempotente de webhooks y sincronización con seña y caja
El sistema MUST procesar de forma estrictamente idempotente las notificaciones por `mp_payment_id` (`RN-PA-03`). Ante un pago `approved`, el sistema MUST transicionar la `Sena` a `cobrada`, registrar el `MovimientoCaja` correspondiente por medio `mp` y actualizar `turno.sena_cobrada = True`. Reintentos posteriores para un mismo `mp_payment_id` MUST responder `200 OK` sin duplicar movimientos ni transicionar nuevamente la seña.

#### Scenario: Pago aprobado actualiza seña y registra movimiento de caja
- **GIVEN** una seña `pendiente` asociada a un turno y un webhook con estado de pago `approved`
- **WHEN** se procesa la notificación por primera vez
- **THEN** la seña pasa a `cobrada`, se genera un `MovimientoCaja` de ingreso con medio `mp` y el turno queda habilitado como `sena_cobrada = True`.

#### Scenario: Reenvío de webhook existente no duplica movimiento ni estado
- **GIVEN** un pago ya procesado previamente con un determinado `mp_payment_id`
- **WHEN** Mercado Pago reenvía el webhook con idéntico `mp_payment_id`
- **THEN** el sistema detecta la idempotencia, responde `200 OK` y no genera movimientos ni transiciones duplicadas.

### Requirement: Detección y registro de discrepancias en pagos extemporáneos o desfasados
El sistema MUST registrar un `CobroMP` con `estado_conciliacion = discrepancia` cuando se recibe un pago aprobado para una seña cuyo estado es `vencida` o cuyo turno ya ha sido cancelado o liberado (`RN-PA-05`). El sistema MUST NOT auto-confirmar un turno vencido ni auto-cerrar la discrepancia, dejándola visible para intervención y resolución manual de recepción o Dueño.

#### Scenario: Pago recibido tras vencimiento de seña se marca como discrepancia
- **GIVEN** un turno cancelado y una seña marcada en estado `vencida`
- **WHEN** se recibe un webhook de Mercado Pago informando un pago aprobado tardío
- **THEN** el sistema registra el cobro en `cobro_mp` con estado `discrepancia`, no confirma el turno y lo expone para resolución manual.
