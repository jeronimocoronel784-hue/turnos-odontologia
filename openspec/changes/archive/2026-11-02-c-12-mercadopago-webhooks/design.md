# Design: `c-12-mercadopago-webhooks`

## Context
Ver motivación en `proposal.md` y especificaciones en `specs/mercadopago-webhooks/spec.md`. `C-11` ya incorporó en el esquema `sena.mp_payment_id` y `movimiento_caja.cobro_mp_id`. Este change implementa la tabla `cobro_mp`, el cliente de Mercado Pago, el endpoint público de webhooks con firma HMAC, la sincronización idempotente con señas y la conciliación diaria (`RN-PA-03`, `RN-PA-05`, `RN-SE-04`).

## UI Mockups
Decision: no (no UI)

## Goals / Non-Goals
**Goals:**
- Creación de preferencias de pago con `external_reference` atada a la seña y expiración sincronizada con `sena.vence_at`.
- Validación criptográfica de firma `x-signature` (HMAC SHA-256) en webhooks de Mercado Pago.
- Persistencia cruda del payload (`JSONB`) para trazabilidad y auditoría.
- Idempotencia estricta en el procesamiento del evento (`mp_payment_id` único).
- Mapeo de estados `approved` y `refunded` sobre `Sena` y `MovimientoCaja`.
- Detección de discrepancias ante pagos tardíos o montos desfasados sin auto-cierre ni daño al estado de turnos.
- Consulta administrativa de cobros y discrepancias bajo `Recurso.CAJA`.

**Non-Goals:**
- Interfaz gráfica o pantalla de pago para el paciente (corresponde a `C-15` en PWA).
- Cobros presenciales mediante terminales físicas MP Point (fuera del alcance del MVP).
- Suscripciones o débitos automáticos recurrentes.

## Decisions

### 1. Cliente HTTP de Mercado Pago desacoplado e inyectable (`MercadoPagoClient`)
- **Decisión**: Implementar una clase `MercadoPagoClient` que encapsule las llamadas a la API REST de Mercado Pago (creación de preferencias, consulta de pagos) y permitir inyectar una versión simulada o mockeada en los tests.
- **Razón**: Permite ejecutar la suite de pruebas completa en entornos offline y en sandbox sin depender de la conectividad externa ni credenciales reales en CI, cumpliendo `R11`.
- **Alternativas consideradas**: Usar directamente el SDK oficial `mercadopago-python`. Descartado como dependencia obligatoria pesada ya que la API REST de Checkout Pro / Webhooks de MP es directa, síncrona/asíncrona y estándar con `httpx`, evitando incompatibilidades de tipos en Python 3.12/3.13.

### 2. Verificación de firma HMAC `x-signature` de Mercado Pago
- **Decisión**: Extraer `ts` y `v1` del encabezado `x-signature`, reconstruir el manifiesto (`id:[data.id];request-id:[x-request-id];ts:[ts];`) y validar mediante `hmac.compare_digest` con el `MP_WEBHOOK_SECRET` del tenant.
- **Razón**: Garantiza autenticidad criptográfica e integridad absoluta contra alteraciones o suplantación (`RN-SE-04`).
- **Alternativas consideradas**: Aceptar payloads sin verificar firma confiando solo en la IP. Descartado tajantemente por ser dominio financiero crítico (`CRITICO`).

### 3. Persistencia cruda antes del procesamiento de negocio
- **Decisión**: Al recibir el webhook, persistir inmediatamente la fila en `cobro_mp` con el payload JSONB crudo antes de evaluar la máquina de estados.
- **Razón**: Si el procesamiento posterior falla o requiere conciliación, el evento no se pierde y queda registrado para reintento o auditoría.
- **Alternativas consideradas**: Procesar en memoria y persistir solo si es exitoso. Descartado: ante fallos de base de datos se pierde el comprobante del webhook.

### 4. Idempotencia y transaccionalidad por `mp_payment_id`
- **Decisión**: Constraint `UniqueConstraint("mp_payment_id")` en base de datos. Ante colisión en `POST /webhooks/mercadopago`, responder `200 OK` inmediatamente registrando que ya fue procesado.
- **Razón**: Cumple estrictamente `RN-PA-03` y las especificaciones de webhooks de Mercado Pago que requieren respuestas 200/201 para frenar el ciclo de reintentos.

## Risks / Trade-offs
- **[Riesgo: Pago extemporáneo post-vencimiento]** → El paciente paga un link vencido cuando el turno ya fue cancelado o liberado a la lista de espera.
  - *Mitigación*: Se registra el pago en `cobro_mp` con `estado_conciliacion = discrepancia` y se emite alerta; no se resucita automáticamente el turno ni se pisa un sobreturno.
- **[Riesgo: Reintentos de webhook en ráfaga]** → Dos peticiones concurrentes para el mismo pago entran simultáneamente.
  - *Mitigación*: La unicidad de `mp_payment_id` a nivel motor PostgreSQL junto con transacciones aisladas garantiza que una única transacción transicione la seña y la otra captura la idempotencia.

## Migration Plan
1. Migración Alembic `011_mercadopago_webhooks.py`: crea la tabla `cobro_mp`, índices, constraints y asigna permisos a `turnos_app`.
2. Rollback probado: `downgrade -1` elimina limpiamente la tabla y permisos.
