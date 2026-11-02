# Proposal: `c-12-mercadopago-webhooks`

## Why
Para que el consultorio odontológico cobre señas de manera automatizada las 24 horas y reduzca el ausentismo (Flujo 1 paso 3, `RN-PA-02`, `RN-PA-03`, `US-031`), el sistema requiere integrarse con la API de Mercado Pago. Es crítico contar con creación de preferencias con expiración vinculada al vencimiento de la seña, recepción de webhooks con verificación criptográfica de firma HMAC, procesamiento idempotente respaldado por persistencia cruda (`mp_payment_id` único), sincronización con la máquina de estados de `Sena` y `MovimientoCaja`, y conciliación diaria con detección de discrepancias sin auto-cierre silencioso (`RN-PA-05`, `RN-SE-04`).

## What Changes
- **Persistencia y Migración `011_mercadopago_webhooks`**:
  - Modelo `CobroMP` (`cobro_mp`): `id`, `tenant_id`, `turno_id` (nullable), `sena_id` (nullable), `mp_payment_id` (único, indexado), `mp_preference_id`, `monto` (Decimal), `estado_mp` (`approved`, `pending`, `rejected`, `refunded`, `cancelled`), `estado_conciliacion` (`pendiente`, `conciliado`, `discrepancia`), `payload` (JSONB para auditoría del webhook crudo), `created_at`.
  - Migración reversible `011_mercadopago_webhooks.py` con tabla, índices (`mp_payment_id`, `(tenant_id, estado_conciliacion)`), foreign keys a `tenant`, `turno`, `sena` y permisos `GRANT/REVOKE` para `turnos_app`.
- **Servicio de Integración Mercado Pago (`MercadoPagoClient` / Service)**:
  - Generación de preferencia de checkout con `external_reference = str(sena.id)`, `expiration_date_to = sena.vence_at.isoformat()`, montos enteros/decimales exactos y metadata de trazabilidad.
  - Verificación de firma HMAC de webhooks (`x-signature`: extracción de `ts` y hash `v1` usando secreto del tenant, `RN-SE-04`).
- **Webhook e Idempotencia (`POST /webhooks/mercadopago`)**:
  - Persistencia inicial del payload crudo antes de procesar reglas de negocio (`knowledge-base/11_pagos_mercadopago.md`).
  - Idempotencia estricta por `mp_payment_id`: si el pago ya fue procesado, responde `200 OK` inmediatamente sin alterar la seña ni duplicar movimientos de caja (`RN-PA-03`).
  - Mapeo de estados:
    - `approved`: marca `Sena` como `cobrada`, registra `MovimientoCaja` de ingreso con medio `MedioPago.MP`, vincula `sena.mp_payment_id = mp_payment_id` y actualiza `turno.sena_cobrada = True` (`RN-PA-01`, `RN-PA-05`).
    - `refunded`: marca `Sena` como `devuelta` y genera movimiento de egreso compensatorio.
    - Pago posterior a vencimiento (`sena.estado == vencida` o expirada): registra `CobroMP` con `estado_conciliacion = discrepancia` para revisión humana y no auto-confirma el turno.
- **Conciliación Diaria y Auditoría**:
  - Tarea/servicio de conciliación: consulta estado de cobros pendientes y compara contra Mercado Pago; discrepancias de monto o estado quedan marcadas para resolución manual.
  - Endpoint administrativo `GET /api/pagos/mercadopago/cobros` y `GET /api/pagos/mercadopago/discrepancias` protegido por `Recurso.CAJA`.

## Capabilities
### New Capabilities
- `mercadopago-webhooks`: Integración con Mercado Pago para cobro de señas, verificación de firma en webhooks, idempotencia por payment ID, conciliación diaria y resolución de discrepancias (`RN-PA-02`, `RN-PA-03`, `RN-PA-05`, `knowledge-base/11_pagos_mercadopago.md`).

## Impact
- **Governance**: `CRITICO` (pagos, transacciones financieras, webhooks e idempotencia de cobros).
- **Dependencias**: Requiere `C-11` (`caja-senas`). Desbloquea `C-15` (`reserva-publica-pwa`) para el pago online de señas.
