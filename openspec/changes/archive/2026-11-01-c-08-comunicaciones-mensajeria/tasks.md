# Tasks: C-08 Comunicaciones y Mensajería (`c-08-comunicaciones-mensajeria`)

## Phase 1: Dominio, Migración 007, Seed de Plantillas y Contratos Pydantic

- [x] 1.1 Crear `src/backend/app/domain/plantilla.py` (`Plantilla`, `CodigoPlantilla`) y `src/backend/app/domain/mensaje.py` (`Mensaje`, `EstadoMensaje`, `CanalMensaje`, `generar_idempotency_key_mensaje`), la migración reversible `src/backend/alembic/versions/007_comunicaciones_mensajeria.py` con `GRANT`/`REVOKE` para `turnos_app`, y extender `src/backend/app/infrastructure/seed.py` con las 5 plantillas base. Registrar modelos en `alembic/env.py` y `tests/conftest.py`. Verificar con `tests/test_migracion_007_comunicaciones.py`.
- [x] 1.2 Crear `src/backend/app/api/schemas_comunicaciones.py` (`PlantillaCreate`, `PlantillaRead`, `MensajeCreate`, `MensajeRead`, `WebhookWhatsAppPayload` con `extra="forbid"` en inputs de gestión) y verificar con `tests/test_schemas_comunicaciones.py`.

## Phase 2: Outbox, Worker, Clientes WA/SMTP y Reglas `RN-CO-01..04`

- [x] 2.1 Implementar los adaptadores `src/backend/app/infrastructure/comunicaciones/wa_client.py` y `src/backend/app/infrastructure/comunicaciones/mailer.py` (sin PHI en logs, `R9`), los casos de uso en `src/backend/app/application/comunicaciones.py` (`encolar_mensaje`, `programar_recordatorio_24h`, `procesar_mensaje_outbox`, `procesar_outbox_pendientes`, `reenviar_mensaje`) y conectar `src/backend/app/workers/main.py`. Verificar deduplicación (`RN-CO-02`), bloqueo sin `optin_wa` (`RN-CO-01`), reintentos con backoff (`RN-CO-03`) y versionado de plantilla (`RN-CO-04`) con `tests/test_comunicaciones_negocio.py`.

## Phase 3: Webhook WhatsApp HMAC y Endpoints Internos (`/api/mensajes`, `/api/plantillas`)

- [x] 3.1 Implementar `src/backend/app/api/routers/comunicaciones.py` con el router interno (`/api/mensajes`, `/api/mensajes/{id}/reenviar`, `/api/mensajes/procesar-outbox`, `/api/plantillas` bajo RBAC `Recurso.MENSAJES`) y el router de webhook (`GET /webhooks/whatsapp`, `POST /webhooks/whatsapp` con validación HMAC-SHA256, confirmación idempotente `RN-AG-08` y baja `STOP` `RN-CO-01`), registrándolos en `src/backend/app/main.py` y `tests/conftest.py`. Verificar con `tests/test_comunicaciones_api.py`.
- [x] 3.2 Actualizar `README.md` y `CHANGES.md` (`[x]` en C-08), y ejecutar `ruff check`, `ruff format --check`, `mypy` y `pytest` completos en verde.
