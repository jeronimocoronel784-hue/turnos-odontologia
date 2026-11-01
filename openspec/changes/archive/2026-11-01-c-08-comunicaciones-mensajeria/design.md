# Design: C-08 Comunicaciones y Mensajería (`c-08-comunicaciones-mensajeria`)

## UI Mockups
Decision: no (no UI)

## Context
El sistema requiere comunicación transaccional y recordatorios por WhatsApp Business Cloud API y correo SMTP (**Flujo 2**) sin bloquear el event loop de FastAPI (`R3`), sin duplicar mensajes ante reintentos (`RN-CO-02`), respetando el consentimiento `optin_wa` (`RN-CO-01`), versionando las plantillas (`RN-CO-04`) y verificando criptográficamente los webhooks entrantes de WhatsApp (`R8`, `RN-AG-08`).

## Decisions

### D1. Tablas `plantilla` y `mensaje` (Outbox transaccional)
- **Decisión**:
  - `plantilla`: almacena `(tenant_id, codigo, canal, version, asunto, cuerpo, activa)` con constraint único `(tenant_id, codigo, canal, version)`. Al crear una nueva versión de un mismo `(codigo, canal)`, se incrementa `version` y el outbox guarda `plantilla_version` y `cuerpo_renderizado` inmutable al momento de encolar (`RN-CO-04`).
  - `mensaje`: almacena el outbox con `idempotency_key` único por `tenant_id`. Las claves siguen el formato determinístico `msg:{entidad_id}:{codigo_plantilla}:{ventana}` (por ejemplo `msg:{turno_id}:recordatorio_24h:24h`). Si `encolar_mensaje` encuentra una fila existente con ese `(tenant_id, idempotency_key)`, la devuelve sin insertar duplicados (`RN-CO-02`).

### D2. Verificación de `optin_wa` en el momento de despacho y estado `omitido`
- **Decisión**: Además de poder validarse al encolar, `procesar_mensaje_outbox` verifica en tiempo de ejecución el estado actual de `paciente.optin_wa` antes de invocar `wa_client`. Si el paciente revocó su `optin_wa` entre que se programó el recordatorio y la hora de envío, el mensaje NO se envía por WhatsApp, pasa a estado `omitido` con `error="Opt-in de WhatsApp inactivo (RN-CO-01)"` y se registra en `auditoria`.

### D3. Backoff exponencial acotado y adaptadores inyectables sin PHI en logs
- **Decisión**: Ante error de transporte en `wa_client` o `mailer`, se incrementa `intentos` y si `intentos < max_intentos` (default `3`), el mensaje permanece en `pendiente` con `programado_para = ahora + timedelta(minutes=5 * (2 ** (intentos - 1)))`. Al alcanzar `max_intentos`, pasa a `fallido` (habilitando a Recepción a usar `POST /api/mensajes/{id}/reenviar`). Los logs solo registran `mensaje_id`, `canal`, `plantilla` y código de estado, jamás DNI, teléfono ni cuerpo clínico (`R9`).

### D4. Webhook de WhatsApp (`GET/POST /webhooks/whatsapp`) con HMAC-SHA256
- **Decisión**:
  - `GET /webhooks/whatsapp` valida `hub.mode == "subscribe"` y `hub.verify_token == settings.wa_webhook_token` usando `hmac.compare_digest`.
  - `POST /webhooks/whatsapp` valida la cabecera `X-Hub-Signature-256` (`sha256=<hex>`) calculando ` hmac.new(secret, raw_body, hashlib.sha256).hexdigest()`. Si no coincide, rechaza con `401 Unauthorized`.
  - Los eventos válidos se deduplican por `event_id` / `wamid` y ejecutan:
    - Confirmación de turno (`CONFIRMAR` + `turno_id` o `token`) → `cambiar_estado_turno(..., nuevo_estado=EstadoTurno.CONFIRMADO, idempotente=True)` (`RN-AG-08`).
    - Baja de opt-in (`STOP` / `BAJA`) → desactiva `optin_wa` en los pacientes con ese teléfono y registra auditoría (`RN-CO-01`).
