# Flujos Principales

Cada flujo se documenta extremo a extremo, mostrando interacciones entre componentes.

## Flujo 1: Reserva online con seña

**Disparador**: paciente abre el link de reserva.
**Actor**: Paciente (sin cuenta).

**Pasos**:
1. [PWA] muestra prestaciones, profesionales y slots reales (duración por prestación, bloqueos y solapamientos descontados).
2. [Paciente] elige slot e ingresa nombre + DNI + teléfono (+ OS/afiliado si tiene).
3. [API] valida anti-solapamiento, crea Paciente (si nuevo), Turno `pendiente` y Seña `pendiente` si la prestación la exige; genera `token_gestion`.
4. [API] encola Mensaje WA/email de confirmación de reserva con link de pago MP y link de gestión.
5. [Paciente] paga seña → webhook MP → [API] marca Cobro conciliado, Seña `cobrada`, Turno habilitado a confirmar.
6. [Worker] programa recordatorio 24 h antes; si la seña vence impaga, [API] libera el slot y avisa lista de espera.

**Diagrama de secuencia** (ASCII):
```
Paciente → PWA → API → DB (turno pendiente + seña pendiente)
Paciente → MP → webhook → API → DB (seña cobrada)
API → Redis(outbox) → WA/email → Paciente
```

**Casos de error**:
- Slot tomado entre tanto → 409 con slots alternativos (RN-GL-02).
- Pago duplicado por reintento → idempotencia por `mp_payment_id`, un solo cobro.
- Seña vencida impaga → turno cancelado + slot liberado + aviso a lista de espera.

## Flujo 2: Confirmación WA con actualización de agenda

**Disparador**: mensaje programado (recordatorio con botones Confirmar/Reprogramar).
**Actor**: Paciente.

**Pasos**:
1. [Worker] toma Mensaje `pendiente` vencido de Redis, verifica opt-in y envía por WA Business API; marca `enviado` con log.
2. [Paciente] toca Confirmar → webhook WA → [API] valida token y pasa Turno a `confirmado` (idempotente).
3. [PWA Recepción] refleja el cambio en vivo en la agenda; si el paciente pide reprogramar, ofrece slots y aplica RN-AG-06.
4. [API] audita cada transición.

**Casos de error**:
- Sin opt-in → no se envía; se registra omisión con motivo.
- Webhook repetido → misma respuesta sin doble transición.
- Reprogramación fuera de término → se ofrece lista de espera o cargo según política.

## Flujo 3: Atención con HC y odontograma

**Disparador**: paciente presente en consultorio.
**Actor**: Odontólogo.

**Pasos**:
1. [Recepción] marca Turno `presente`; [API] verifica consentimiento si la prestación es invasiva (bloquea si falta).
2. [Odontólogo] abre ficha: anamnesis, odontograma FDI, evoluciones previas y presupuesto del plan.
3. [Odontólogo] registra eventos por pieza/superficie vinculados al turno + adjuntos (RX/fotos) + evolución.
4. [Odontólogo] indica próxima cita (se crea Turno vinculado al plan) o da alta.
5. [API] cierra Turno `finalizado`; deja el turno liquidable (OS) y audita todo.

**Casos de error**:
- Sin consentimiento firmado → bloqueo con opción de firmar en el acto (presencial/token).
- Edición de HC pasada → se crea nueva evolución correctiva, nunca se pisa (RN-CL-01).

## Flujo 4: Cobro con seña aplicada (MP conciliado)

**Disparador**: atención finalizada con seña cobrada.
**Actor**: Recepción.

**Pasos**:
1. [API] calcula total: `precio − cobertura_OS − seña_cobrada = saldo`.
2. [Recepción] cobra saldo por el medio que sea (MP/efectivo/tarjeta/transf); [API] crea Cobro + Movimiento conciliado.
3. [API] marca Seña `aplicada` y vincula todo al Cierre abierto.
4. [Dueño/Recepción] cierra caja: compara total sistema vs contado; diferencia visible; cierre inmutable.

**Casos de error**:
- Monto MP ≠ esperado → `discrepancia` para revisión manual, no auto-cierra.
- Cierre con diferencia → se registra y se audita; reapertura solo Dueño.

## Flujo 5: Liquidación OS con débitos

**Disparador**: cierre de período (mensual por OS).
**Actor**: Administración.

**Pasos**:
1. [API] junta turnos `finalizado` con OS del período, calcula reclamado por arancel vigente.
2. [Administración] revisa, marca débitos con motivo si la OS recorta, y presenta.
3. [API] genera exportación CSV/JSON de la liquidación + detalle por turno.
4. Estados: `borrador → presentada → pagada | con_debitos`.

**Casos de error**:
- Arancel vencido → se alerta y se usa el vigente con aviso (RN-OS-01).
- Turno en dos liquidaciones → rechazado por constraint (RN-OS-02).

## Flujo 6: Lista de espera que rellena cancelaciones

**Disparador**: cancelación o no-show que libera slot.
**Actor**: Sistema (con paciente).

**Pasos**:
1. [API] libera el slot y busca primera entrada `activa` compatible (prestación/sillón/profesional).
2. [API] encola aviso WA/email con ventana de respuesta; marca entrada `avisada` (idempotente).
3. [Paciente] acepta por token → [API] crea Turno vinculado, marca `colocada`.
4. Si vence la ventana → siguiente entrada; si nadie acepta → slot libre para reserva.

**Casos de error**:
- Doble aceptación simultánea → gana la primera; la otra recibe alternativa.
- Paciente dado de baja → se salta sin romper el orden.

## Flujo 7: Auditoría y exportación

**Disparador**: consulta del Dueño o pedido de portabilidad.
**Actor**: Dueño.

**Pasos**:
1. [Dueño] filtra Auditoría por entidad/período/actor en la PWA.
2. [API] devuelve trail append-only (quién/qué/cuándo/antes/después).
3. [Dueño] exporta agenda/pacientes/caja/liquidaciones en CSV/JSON en 1 clic.

**Casos de error**:
- Exportación grande → job asíncrono con descarga cuando termina.
- Intento de borrar auditoría → rechazado por permiso + constraint.
