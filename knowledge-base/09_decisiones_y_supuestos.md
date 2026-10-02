# Decisiones y Supuestos

## Decisiones documentadas

### DD-01 — PWA + web en vez de app nativa
**Decisión**: Frontend React+Vite como SPA responsive + PWA instalable (móvil y desktop); sin desarrollo nativo iOS/Android.
**Contexto**: El paciente reserva desde el celular y el consultorio necesita instalación simple; presupuesto acotado.
**Alternativas consideradas**: App nativa; solo web responsive sin PWA; TWA empaquetada.
**Justificación**: La PWA cubre reserva, gestión por token y agenda con un solo código; los 18 competidores muestran que la reserva sin app obligatoria convierte mejor (DentalSoft/FLAP).
**Trade-offs aceptados**: Sin push en v1 (WA/email en su lugar); funcionalidad offline limitada a caché/cola básica.

### DD-02 — Monolito API FastAPI + front desacoplado
**Decisión**: Un solo backend FastAPI modular + SPA separada, todo en Docker Compose.
**Contexto**: Equipo chico, velocidad de entrega como prioridad (P5), piloto con 1 consultorio.
**Alternativas consideradas**: Microservicios; backend monolítico con templates server-side.
**Justificación**: Menos infraestructura, un deploy, contratos REST claros para la PWA; se parte solo si pagos o colas lo exigen.
**Trade-offs aceptados**: Deuda técnica interna aceptada; escalado vertical al inicio.

### DD-03 — JWT access+refresh con rotación
**Decisión**: Access corto + refresh rotativo (reúso detectado = revocación de la cadena).
**Contexto**: Sesiones de recepción/odontólogo todo el día en dispositivos compartidos.
**Alternativas consideradas**: Sesiones server-side; access largo sin refresh.
**Justificación**: Sin estado de sesión en DB, revocación efectiva ante robo, estándar probado.
**Trade-offs aceptados**: Implementación de rotación y lista de revocación; logout global requiere endpoint explícito.

### DD-04 — RBAC simple de 4 roles
**Decisión**: Dueño / Recepción / Odontólogo / Paciente-por-token, matriz fija en §03.
**Contexto**: Consultorio PyME 1–10 sillones; permisos por recurso claros.
**Alternativas consideradas**: Permisos granulares por usuario; ABAC por atributos.
**Justificación**: Cubre el 100% de los casos v1 sin panel de permisos complejo; auditable.
**Trade-offs aceptados**: Casos raros (ej. higienista) se mapean a un rol existente hasta v2.

### DD-05 — Sin AFIP nativa en v1 (exportación conciliable)
**Decisión**: v1 exporta liquidaciones/movimientos en CSV/JSON; conector fiscal AFIP/ARCA en v2.
**Contexto**: Ningún SaaS AR relevado tiene AFIP comprobada; prometerla sin conector certificado destruye confianza (Discovery riesgo 4).
**Alternativas consideradas**: Integrar facturador externo en v1; prometer AFIP en marketing.
**Justificación**: Honestidad como diferencial ("Cumplimiento verificable"); el exportador deja v2 sin re-trabajo de datos.
**Trade-offs aceptados**: Doble carga parcial de facturación durante v1; mensaje comercial cuidadoso.

### DD-06 — Cola Redis con outbox e idempotencia
**Decisión**: Redis (RQ/Celery o ARQ) + tabla outbox con `idempotency_key` para WA/email, vencimientos y reintentos.
**Contexto**: No puede haber doble cobro de seña ni doble recordatorio; los proveedores fallan.
**Alternativas consideradas**: Envío síncrono en el request; cron sin outbox.
**Justificación**: Reintentos seguros, límites de costo WA visibles, tolerancia a caídas.
**Trade-offs aceptados**: Operar Redis desde día 1; monitoreo de colas necesario.

### DD-07 — Multi-tenant lógico desde día 1
**Decisión**: `tenant_id` en toda tabla de negocio + tests de aislación; piloto con 1 tenant.
**Contexto**: Escala confirmada multi-tenant (P0-scale), pero primer cliente único.
**Alternativas consideradas**: Mono-tenant y migrar después; schema-por-tenant.
**Justificación**: El costo de agregar la columna hoy es mínimo; migrar después es carísimo. Schema-por-tenant se evalúa si un cliente grande lo exige.
**Trade-offs aceptados**: Filtros obligatorios en cada query (enforced por helper, no por memoria).

## Supuestos inferidos

### SU-01 — Paciente móvil-first sin cuenta
**Supuesto**: El paciente prefiere reservar con DNI+teléfono sin crear cuenta.
**Origen**: Discovery Anexo §11 + Q&A P3; patrón DentalSoft/FLAP.
**Riesgo si es falso**: Fricción o cuentas duplicadas.
**Cómo validar**: Piloto: % reservas completadas sin ayuda vs abandonos.

### SU-02 — WA automático paga su costo
**Supuesto**: Recordatorios + lista de espera bajan ausentismo lo suficiente para cubrir el costo por mensaje.
**Origen**: Discovery riesgos §10; Q&A P7.
**Riesgo si es falso**: Margen erosionado por mensajes.
**Cómo validar**: Medir ausentismo pre/post y costo WA por turno recuperado en el piloto.

### SU-03 — Seña aceptada por el paciente
**Supuesto**: El paciente argentino acepta seña por MP a cambio de turno asegurado.
**Origen**: FLAP lo valida parcialmente; Discovery riesgo 1.
**Riesgo si es falso**: Caída de conversión online.
**Cómo validar**: A/B seña exigible vs opcional por prestación en piloto.

### SU-04 — Padrón OS mantenible
**Supuesto**: Un padrón configurable por tenant (sin integración oficial) alcanza para v1.
**Origen**: Discovery vacíos §C.3; solo DentalSoft lo declara.
**Riesgo si es falso**: Aranceles desactualizados generan reclamos.
**Cómo validar**: Revisión mensual de aranceles con el piloto; medir débitos por desactualización.

### SU-05 — Onboarding en 1 día
**Supuesto**: Plantillas + importación Excel permiten migrar un consultorio en una jornada.
**Origen**: Discovery riesgos §10 (abandono si no).
**Riesgo si es falso**: Recepción abandona.
**Cómo validar**: Cronometrar onboarding del piloto; iterar importador.

### SU-06 — Internet inestable tolerable con PWA
**Supuesto**: Caché/cola básica de PWA + backend local/Docker alcanza; no hace falta offline-first total (estilo Odontoly) en v1.
**Origen**: Discovery restricción 2; Q&A P0-sys.
**Riesgo si es falso**: Consultorios con mala conexión sufren.
**Cómo validar**: Probar piloto con throttling; medir errores de red por día.
