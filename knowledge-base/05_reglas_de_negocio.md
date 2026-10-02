# Reglas de Negocio

Cada regla tiene un código único `RN-{DOMINIO}-{NN}` para trazabilidad. Fuente principal: `discovery/discovery.md` Anexo §7 + Q&A P6/P7 confirmadas.

## Dominio: Agenda (RN-AG)

- **RN-AG-01**: No puede existir doble reserva: ningún solapamiento de rangos `[inicio, fin)` para el mismo profesional ni para el mismo sillón, salvo turno con `sobreturno = true`. — Evita el dolor central (dobles reservas).
- **RN-AG-02**: La duración de la prestación manda sobre cualquier default; `fin = inicio + duracion_prestacion` salvo override explícito auditado.
- **RN-AG-03**: Los slots cubiertos por un Bloqueo (feriado/vacaciones/manual) no son reservables por ningún canal.
- **RN-AG-04**: El sobreturno solo existe si es explícito y marcado (`sobreturno = true` + motivo); nunca se crea en silencio.
- **RN-AG-05**: Cancelación/reprogramación exigen anticipación mínima configurable (default 24 h); fuera de término el turno pasa a `ausente` o genera cargo según política del tenant.
- **RN-AG-06**: Reprogramar no muta el turno original: lo pasa a `reprogramado` y crea un turno nuevo con `turno_origen_id`; el historial queda completo.
- **RN-AG-07**: Máquina de estados de turno (grafo cerrado): `pendiente → confirmado → presente → finalizado`; ramas: `pendiente|confirmado → cancelado | ausente | reprogramado`. Transiciones fuera del grafo se rechazan. `finalizado` es terminal y habilita liquidación.
- **RN-AG-08**: La confirmación por WhatsApp (botón/token) actualiza sola el estado a `confirmado`, con idempotencia (mismo evento dos veces = un solo cambio).

## Dominio: Lista de espera (RN-LE)

- **RN-LE-01**: Orden de ofrecimiento por (`prioridad`, `created_at`); el aviso se envía a una entrada por vez con ventana de respuesta configurable.
- **RN-LE-02**: Un hueco liberado genera como máximo un aviso por entrada (idempotencia por `idempotency_key`); si vence la ventana, se avisa a la siguiente.
- **RN-LE-03**: Colocar un aviso aceptado crea el Turno vinculado y marca la entrada `colocada`; el hueco deja de ofrecerse.

## Dominio: Señas y cobros (RN-PA)

- **RN-PA-01**: La seña vive atada a la cita: estados `pendiente → cobrada → aplicada | devuelta`, más `vencida`. Un turno con seña exigible impaga no pasa a `confirmado`.
- **RN-PA-02**: Si la prestación tiene `requiere_sena`, la reserva genera la Seña en `pendiente` con link/QR de Mercado Pago y vencimiento.
- **RN-PA-03**: Idempotencia de pagos: `mp_payment_id` único; un webhook repetido no crea un segundo cobro ni cambia la seña dos veces.
- **RN-PA-04**: Cancelación dentro de término con seña cobrada → `devuelta` (o a cuenta, según política); cancelación fuera de término / ausente → la seña se retiene y se `aplica` a gastos.
- **RN-PA-05**: Todo cobro genera su Movimiento de caja conciliado; discrepancia de montos marca `discrepancia` y no cierra sola.

## Dominio: Obra social (RN-OS)

- **RN-OS-01**: En cada turno con OS se calcula `a_cargo = precio − cobertura`; sin cobertura vigente se factura como particular.
- **RN-OS-02**: Solo turnos `finalizado` entran en liquidación; un turno figura en una sola liquidación abierta por OS/período.
- **RN-OS-03**: Alcance v1: cálculo + liquidación exportable (CSV/JSON) con control de débitos; sin presentación electrónica (v2).

## Dominio: Clínica (RN-CL)

- **RN-CL-01**: La HC no admite hard delete: se corrige con nueva Evolución; el historial por pieza del odontograma es inmutable (nuevos eventos, nunca UPDATE destructivo).
- **RN-CL-02**: Prestación marcada `invasiva` exige Consentimiento firmado previo al turno; sin firma no se puede iniciar la atención (`presente` bloqueado con mensaje claro).
- **RN-CL-03**: Recepción no edita contenido clínico (solo lectura); el registro clínico es de rol odontólogo/dueño.
- **RN-CL-04**: Presupuesto aceptado con invasiva exige consentimiento; los items del plan se vinculan a sus turnos.

## Dominio: Comunicación (RN-CO)

- **RN-CO-01**: Opt-in WA obligatorio: ningún mensaje automático sale sin `optin_wa = true`; la baja (STOP) corta envíos salvo transaccionales exigidos.
- **RN-CO-02**: Sin doble recordatorio: un (`turno`, `plantilla`, `ventana`) genera un solo envío (outbox + `idempotency_key`); reintentos no duplican.
- **RN-CO-03**: Sin push en v1: los canales automáticos son WA + email encolados en Redis; el envío es asíncrono con reintentos y log.
- **RN-CO-04**: Toda plantilla tiene versión; el log guarda qué texto se envió a quién y cuándo.

## Dominio: Seguridad y cumplimiento (RN-SE)

- **RN-SE-01**: Auditoría append-only: todo cambio en turnos/HC/caja registra quién/qué/cuándo/antes/después; sin UPDATE ni DELETE sobre la tabla.
- **RN-SE-02**: Datos de salud bajo Ley 25.326 + Ley HCE: control de acceso por rol, trazabilidad, exportación del paciente y página legal pública.
- **RN-SE-03**: Tokens públicos (`token_gestion`) con entropía suficiente y vencimiento; no exponen datos de terceros.
- **RN-SE-04**: Secretos (JWT, MP, WA, DB) solo por variables de entorno; nunca en código ni en logs.

## Dominio: Excepciones globales

- **RN-GL-01**: Ante conflicto entre reglas, el orden de precedencia es: seguridad/cumplimiento (RN-SE) > clínica (RN-CL) > cobros (RN-PA) > agenda (RN-AG) > comunicación (RN-CO).
- **RN-GL-02**: Todo rechazo por regla devuelve mensaje accionable en español rioplatense (qué pasó, por qué, cómo seguir), nunca un código crudo.
- **RN-GL-03**: Velocidad de entrega acepta deuda técnica en código interno, jamás en RN-SE/RN-CL/RN-PA-03: esas no se atajan.
