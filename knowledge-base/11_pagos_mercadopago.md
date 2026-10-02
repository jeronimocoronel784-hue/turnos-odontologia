# Pagos con Mercado Pago (extra)

> Anexo operativo de §04 (Seña/CobroMP) y §07 Flujos 1/4. No es canónico; existe porque el dominio (seña atada al turno) lo exige.

## Modelo

- Por reserva con `requiere_sena`: se crea `Preferencia` (link/QR) por el monto de la seña, con `external_reference = seña.id` y vencimiento = `vence_at`.
- Webhook `payment` → persistir payload crudo → verificar firma → procesar idempotente por `mp_payment_id`.
- Estados MP (`approved`, `pending`, `rejected`, `refunded`) se mapean a Seña (`cobrada`, `pendiente`, `vencida`, `devuelta`) y a `estado_conciliacion` del Cobro.

## Idempotencia y conciliación

- `mp_payment_id` único: webhook repetido = 200 sin efecto.
- Job diario: compara Cobros `pendientes` contra API MP; marca `conciliado` o `discrepancia` (monto/estado distinto → revisión manual, nunca auto-cierre).
- Devoluciones: solo vía API con motivo + auditoría; la Seña pasa a `devuelta` únicamente cuando MP confirma `refunded`.

## Casos borde

- Paciente paga después del vencimiento → se crea Cobro `discrepancia` y se ofrece aplicar a nuevo turno o devolver.
- Turno cancelado en término con seña cobrada → devolución o saldo a favor según política del tenant.
- Modo prueba: credenciales sandbox por tenant en config (nunca en código).

## Checklist de implementación

- [ ] SDK MP + preference con `external_reference` y `expiration_date_to`.
- [ ] Webhook con verificación de firma + persistencia cruda + worker idempotente.
- [ ] Mapeo de estados + job de conciliación diaria + vista de discrepancias.
- [ ] Links/QR en mensajes WA/email (plantillas US-010/031).
- [ ] Documentar costos MP por operación para pricing (PO-02).
