# Funcionalidades

Organizadas por **épica** y luego por **historia de usuario** (formato US-NNN). MVP = Épicas 1–6 imprescindibles + 7 en base; Épica 8 y 9 explícitamente postergadas (ver Discovery D.3).

## Épica 1: Agenda y reserva online (MVP imprescindible)

### US-001 — Ver agenda multi-profesional/sillón
**Como** recepción **Quiero** ver la agenda diaria/semanal por profesional y sillón con estados y bloqueos **Para** ocupar cada hueco sin solapamientos.
**Criterios de aceptación**:
- [ ] CA-1 Vista día/semana por profesional y por sillón con duraciones reales.
- [ ] CA-2 Bloqueos visibles y no reservables; sobreturnos marcados.
- [ ] CA-3 Reprogramación en 1 clic con historial (RN-AG-06).
**Reglas relacionadas**: RN-AG-01, RN-AG-02, RN-AG-03, RN-AG-04, RN-AG-06.

### US-002 — Reservar online 24/7
**Como** paciente **Quiero** reservar desde link/embed sin registrarme (nombre + DNI + teléfono) **Para** asegurar mi turno sin llamar.
**Criterios de aceptación**:
- [ ] CA-1 Slots reales según prestación/profesional/sillón; sin doble reserva.
- [ ] CA-2 Si la prestación exige seña, la reserva genera link de pago MP.
- [ ] CA-3 Token de gestión para confirmar/cancelar/reprogramar.
**Reglas relacionadas**: RN-AG-01, RN-AG-02, RN-AG-05, RN-PA-01, RN-PA-02.

### US-003 — Lista de espera que rellena huecos
**Como** recepción **Quiero** que al liberarse un hueco se avise solo al siguiente en lista **Para** no perder el slot.
**Criterios de aceptación**:
- [ ] CA-1 Orden por prioridad/antigüedad con ventana de respuesta.
- [ ] CA-2 Aceptar crea el turno y cierra el ofrecimiento.
**Reglas relacionadas**: RN-LE-01, RN-LE-02, RN-LE-03.

## Épica 2: Comunicación automática WA/email (MVP imprescindible)

### US-010 — Confirmación y recordatorios automáticos
**Como** recepción **Quiero** que la confirmación WA actualice sola la agenda y salgan recordatorios programados **Para** no llamar uno por uno.
**Criterios de aceptación**:
- [ ] CA-1 Confirmación por botón WA/token → estado `confirmado` (idempotente).
- [ ] CA-2 Recordatorio 24 h + personalizable por plantilla; log visible.
- [ ] CA-3 Solo con opt-in; baja STOP respetada.
**Reglas relacionadas**: RN-AG-08, RN-CO-01, RN-CO-02, RN-CO-03, RN-CO-04.

### US-011 — Política de cancelación configurable
**Como** dueño **Quiero** definir anticipación mínima y cargo por no-show **Para** proteger la agenda.
**Criterios de aceptación**:
- [ ] CA-1 Anticipación configurable por tenant; mensaje claro al paciente.
- [ ] CA-2 Seña retenida/aplicada según término (RN-PA-04).
**Reglas relacionadas**: RN-AG-05, RN-PA-04, RN-GL-02.

## Épica 3: Ficha clínica y odontograma (MVP imprescindible)

### US-020 — Ficha + anamnesis + evolución
**Como** odontólogo **Quiero** registrar anamnesis y evolución en la cita **Para** no duplicar carga.
**Criterios de aceptación**:
- [ ] CA-1 Ficha única por paciente; evoluciones fechadas e inmutables.
- [ ] CA-2 Solo rol clínico edita; recepción solo lee.
**Reglas relacionadas**: RN-CL-01, RN-CL-03, RN-SE-01.

### US-021 — Odontograma FDI funcional
**Como** odontólogo **Quiero** marcar eventos por pieza/superficie con historial **Para** ver la boca de un vistazo.
**Criterios de aceptación**:
- [ ] CA-1 Nomenclatura FDI 11–48 + superficies; historial por pieza.
- [ ] CA-2 Eventos vinculados al turno que los originó; adjuntos RX/fotos/PDF.
**Reglas relacionadas**: RN-CL-01.

### US-022 — Presupuestos y planes vinculados
**Como** odontólogo **Quiero** presupuestar y vincular items a citas **Para** seguir el plan hasta el alta.
**Criterios de aceptación**:
- [ ] CA-1 Items con precio, cobertura OS y a cargo; estados hasta finalizado.
- [ ] CA-2 Aceptación con consentimiento si hay invasiva.
**Reglas relacionadas**: RN-CL-04, RN-OS-01.

### US-023 — Consentimiento firmado obligatorio
**Como** dueño **Quiero** exigir firma previa en prestaciones invasivas **Para** cumplir y cubrirme legalmente.
**Criterios de aceptación**:
- [ ] CA-1 Sin firma no se inicia la atención; firma presencial o por token.
- [ ] CA-2 Texto versionado + hash + fecha; revocación auditada.
**Reglas relacionadas**: RN-CL-02.

## Épica 4: Caja, señas y Mercado Pago (MVP imprescindible)

### US-030 — Caja diaria con cierre
**Como** recepción **Quiero** registrar cobros/gastos por medio y cerrar caja **Para** que no descuadre nunca.
**Criterios de aceptación**:
- [ ] CA-1 Movimientos por medio (efectivo/débito/crédito/transf/MP); cierre con diferencia visible.
- [ ] CA-2 Cierre cerrado inmutable; reapertura solo Dueño + auditoría.
**Reglas relacionadas**: RN-PA-05, RN-SE-01.

### US-031 — Seña vinculada al turno con MP
**Como** administración **Quiero** exigir seña por prestación y cobrarla por MP conciliado **Para** bajar ausentismo.
**Criterios de aceptación**:
- [ ] CA-1 Seña auto-generada con link/QR y vencimiento; turno impago no confirma.
- [ ] CA-2 Webhook idempotente; estados aplicada/devuelta/vencida según regla.
**Reglas relacionadas**: RN-PA-01, RN-PA-02, RN-PA-03, RN-PA-04.

## Épica 5: Obra social básica (MVP imprescindible)

### US-040 — Cobertura calculada en el turno
**Como** recepción **Quiero** ver cobertura vs particular al agendar **Para** informar el costo real.
**Criterios de aceptación**:
- [ ] CA-1 Padrón configurable (OS × prestación × arancel × copago × vigencia).
- [ ] CA-2 Sin cobertura vigente → particular.
**Reglas relacionadas**: RN-OS-01.

### US-041 — Liquidación exportable con débitos
**Como** administración **Quiero** cerrar liquidación por OS/período y exportarla **Para** presentar sin planilla.
**Criterios de aceptación**:
- [ ] CA-1 Solo turnos finalizados; control de débitos con motivo.
- [ ] CA-2 Exportación CSV/JSON; sin presentación electrónica en v1.
**Reglas relacionadas**: RN-OS-02, RN-OS-03.

## Épica 6: Roles, auditoría y exportación (MVP imprescindible)

### US-050 — RBAC simple y multi-sucursal elemental
**Como** dueño **Quiero** 4 roles con permisos claros y sucursal básica **Para** que cada uno vea lo suyo.
**Criterios de aceptación**:
- [ ] CA-1 Matriz de §03 enforced en API y UI; multi-sucursal por campo `sucursal`.
**Reglas relacionadas**: RN-SE-02.

### US-051 — Auditoría y exportación verificables
**Como** dueño **Quiero** ver quién cambió qué/cuándo y exportar todo en 1 clic **Para** confianza y portabilidad.
**Criterios de aceptación**:
- [ ] CA-1 Auditoría append-only consultable por entidad/período.
- [ ] CA-2 Exportación CSV/JSON de agenda, pacientes, caja, liquidaciones.
**Reglas relacionadas**: RN-SE-01, RN-SE-02.

## Épica 7: Diferenciales del MVP (ganan contra los 18)

- **US-060** Seña + MP atada al turno desde el día 1 (US-031).
- **US-061** OS sin planilla: padrón + débitos (US-040/041).
- **US-062** WA honesto con costos visibles + lista de espera auto (US-010/003).
- **US-063** Precio ARS publicado + onboarding en 1 día (plantillas + importación Excel) + tolerancia a internet inestable (cola offline en PWA).
- **US-064** Exportación + auditoría + firma desde v1 (US-051/023).

## Épica 8: Postergado v2 (explícitamente NO MVP)

- Periodontograma avanzado; ortodoncia/endo/cirugía profundas; IA diagnóstica; dictado por voz.
- Facturación electrónica AFIP/ARCA nativa (v1: exportación conciliable).
- Recepcionista IA por voz; campañas/recupero con scoring; marketing automation.
- Stock/inventario; laboratorio; comisiones complejas; consolidación multi-cadena.
- APIs públicas/marketplace; Google Calendar bidireccional; radiología directa; app nativa; push; portal avanzado.

> Regla de corte (Discovery D.3): si no reduce ausentismo, no acelera el cobro o no evita doble carga (agenda↔HC↔caja↔OS), va a backlog.
