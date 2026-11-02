# Tasks: `c-12-mercadopago-webhooks`

## 1. Modelo de datos, migración y schemas

- [x] 1.1 **Modelo `CobroMP` y migración reversible `011_mercadopago_webhooks`** (TDD)
  - Crear `src/backend/app/domain/mercadopago.py` con `CobroMP`, `EstadoMP` (`approved`, `pending`, `rejected`, `refunded`, `cancelled`) y `EstadoConciliacionMP` (`pendiente`, `conciliado`, `discrepancia`).
  - Crear migración `src/backend/alembic/versions/011_mercadopago_webhooks.py` con tabla `cobro_mp`, índices (`mp_payment_id`, `(tenant_id, estado_conciliacion)`), foreign keys y permisos `GRANT/REVOKE` para `turnos_app`. Registrar en `alembic/env.py` y `tests/conftest.py`.
  - Verificar con test de migración reversible `upgrade head` / `downgrade -1`.

- [x] 1.2 **Schemas Pydantic v2 para Mercado Pago (`extra='forbid'`, `R1`, `R8`)** (TDD)
  - Crear `src/backend/app/api/schemas_mercadopago.py` con `PreferenciaCreate`, `PreferenciaRead`, `WebhookPayloadMP`, `CobroMPRead`, `DiscrepanciaMPRead`.
  - Verificar con `tests/test_schemas_mercadopago.py` (validaciones estrictas, rechazo de campos extra y tipos decimales).

## 2. Cliente de integración, webhook con HMAC e idempotencia

- [x] 2.1 **Cliente y servicio de Mercado Pago con verificación de firma HMAC** (TDD)
  - Implementar en `src/backend/app/infrastructure/mercadopago/client.py` y `src/backend/app/application/mercadopago.py` la creación de preferencias con `external_reference` y `expiration_date_to`, y la verificación criptográfica de `x-signature` (`RN-SE-04`).
  - Verificar con `tests/test_mercadopago_cliente.py` (cálculo de HMAC, rechazo de firmas alteradas y generación de preferencia con expiración).

- [x] 2.2 **Endpoint `POST /webhooks/mercadopago` con persistencia cruda e idempotencia** (TDD)
  - Crear endpoint público de webhook en `src/backend/app/api/routers/webhooks_mercadopago.py` que persista el payload crudo (`JSONB`), valide idempotencia por `mp_payment_id` (`RN-PA-03`), actualice `Sena` a `cobrada`, cree `MovimientoCaja(medio=mp)` y marque `turno.sena_cobrada = True`.
  - Verificar con `tests/test_mercadopago_webhook.py` (procesamiento exitoso de `approved`, respuesta `200` sin re-ejecución ante webhook duplicado, manejo de `refunded`).

## 3. Conciliación, discrepancias y endpoints de administración

- [x] 3.1 **Detección de discrepancias en pagos extemporáneos y conciliación** (TDD)
  - Implementar detección de pago sobre seña `vencida` o turno cancelado marcando `CobroMP` con `estado_conciliacion = discrepancia` sin auto-confirmación (`RN-PA-05`), junto con el servicio de conciliación periódica.
  - Verificar con `tests/test_mercadopago_conciliacion.py`.

- [x] 3.2 **Endpoints de consulta bajo `Recurso.CAJA`, calidad y documentación** (TDD)
  - Crear endpoints administrativos `/api/pagos/mercadopago/cobros` y `/api/pagos/mercadopago/discrepancias` protegidos con RBAC de caja.
  - Verificar con `tests/test_mercadopago_api.py` (roles Dueño/Recepción con acceso, odontólogo con `403`).
  - Ejecutar verificación de calidad (`ruff`, `mypy`, suite completa de pruebas) y documentar en `README.md` y `CHANGES.md`.
