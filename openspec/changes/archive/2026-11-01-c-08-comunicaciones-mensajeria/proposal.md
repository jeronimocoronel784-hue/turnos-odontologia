# Proposal: C-08 Comunicaciones y Mensajería (`c-08-comunicaciones-mensajeria`)

## Why

La reducción del ausentismo en el consultorio odontológico depende de recordatorios automáticos 24 horas antes del turno y confirmación en 1 toque por WhatsApp o email (**Flujo 2**). Para evitar dobles envíos ante caídas de red, respetar el consentimiento obligatorio de WhatsApp (`optin_wa`, `RN-CO-01`) y mantener trazabilidad exacta de qué texto versionado se envió (`RN-CO-04`), se requiere el patrón **Outbox + Worker Redis** con claves de idempotencia (`RN-CO-02`, `RN-CO-03`) y un webhook de WhatsApp verificado con firma HMAC (`RN-AG-08`).

## What Changes

1. **Dominio, Migración `007_comunicaciones_mensajeria` y Seed de 5 Plantillas**:
   - Modelo `Plantilla` (`src/backend/app/domain/plantilla.py`): plantillas versionadas por `(tenant_id, codigo, canal, version)` para los 5 eventos canónicos (`confirmacion_reserva`, `recordatorio_24h`, `cancelacion_turno`, `hueco_lista_espera`, `sena_pendiente`).
   - Modelo `Mensaje` (`src/backend/app/domain/mensaje.py`): tabla outbox con `idempotency_key` único por tenant, `canal` (`wa`, `email`), `plantilla`, `plantilla_version`, `cuerpo_renderizado`, `estado` (`pendiente`, `enviado`, `entregado`, `leido`, `fallido`, `omitido`), `intentos`, `programado_para`, `enviado_at` y `error`.
   - Migración reversible `007_comunicaciones_mensajeria.py` encadenada a `006_lista_espera` con permisos `GRANT`/`REVOKE` para `turnos_app` y extensión de `ejecutar_seed` con las 5 plantillas base.
2. **Motor Outbox, Worker Redis, Clientes WA/SMTP y Reglas `RN-CO-01..04`**:
   - Adaptadores `wa_client.py` y `mailer.py` sin exposición de PHI en logs (`R9`).
   - Casos de uso en `src/backend/app/application/comunicaciones.py`:
     - `encolar_mensaje` y `programar_recordatorio_24h` con deduplicación estricta por `idempotency_key` (`RN-CO-02`).
     - `procesar_outbox_pendientes`: verifica `optin_wa` antes de enviar por WhatsApp (`RN-CO-01`: si no tiene opt-in, registra omisión auditada o usa fallback email sin enviar WA), ejecuta reintentos con backoff exponencial ante fallos transitorios (`RN-CO-03`) y guarda el texto exacto enviado con su versión (`RN-CO-04`).
   - Conexión del worker `src/backend/app/workers/main.py` al procesador de outbox.
3. **Webhook de WhatsApp (`GET/POST /webhooks/whatsapp`) y Router Interno (`/api/mensajes`)**:
   - Verificación de challenge `GET /webhooks/whatsapp` y validación de firma HMAC `X-Hub-Signature-256` en `POST /webhooks/whatsapp`.
   - Procesamiento idempotente de confirmación de turno (`RN-AG-08`), comando `STOP`/`BAJA` que desactiva `optin_wa` (`RN-CO-01`) y actualización de estados de entrega.
   - Endpoints internos `/api/mensajes`, `/api/mensajes/{id}/reenviar`, `/api/mensajes/procesar-outbox` y `/api/plantillas` protegidos por RBAC (`Recurso.MENSAJES`).

## Capabilities

### New Capabilities
- `comunicaciones-mensajeria`: Outbox transaccional de mensajes WA/email con plantillas versionadas, respeto de `optin_wa`, reintentos con backoff sin duplicación y webhook de WhatsApp con firma HMAC.

### Modified Capabilities
- Ninguna spec existente modifica sus requisitos normativos.

## Impact

- **Base de datos**: Nuevas tablas `plantilla` y `mensaje` en migración `007_comunicaciones_mensajeria`.
- **Seguridad y Privacidad (`R8`, `R9`, `RN-SE-04`)**: Verificación obligatoria de firma HMAC en webhook WA, deduplicación por `idempotency_key` / event-id y prohibición de loguear DNI, teléfonos o texto clínico.
