# Actores y Roles

## Actores del sistema

| Actor | Descripción | Cómo interactúa |
|---|---|---|
| Paciente | Persona que reserva atención; puede no tener cuenta (v1: nombre + DNI + teléfono) | Rutas públicas: link de reserva, gestión de su turno por token, confirmación WA por botón, pago de seña MP, firma de consentimiento |
| Recepción / Admin | Personal del consultorio que gestiona agenda, confirma turnos, cobra y liquida | Web/PWA autenticada: agenda multi-profesional, pacientes, caja, OS, reportes |
| Odontólogo | Profesional que atiende y registra clínica | Web/PWA autenticada: su agenda, ficha/HC, odontograma, evoluciones, presupuestos |
| Dueño | Responsable del consultorio/tenant; configura y audita | Web autenticada: configuración, usuarios/roles, reportes, auditoría, exportación |
| (Futuro, no v1) OS / laboratorio | Consumen liquidaciones/derivaciones | Sin acceso en v1; vía exportación |

RBAC simple rol → permisos. Un usuario tiene un rol por tenant; el Dueño puede además tener rol operativo (ej. odontólogo dueño).

## RBAC — Matriz de permisos

| Recurso | Dueño | Recepción | Odontólogo | Paciente (token) |
|---|---|---|---|---|
| Configuración tenant (prestaciones, precios, horarios, políticas, OS) | CRUD | R | R (sus horarios) | — |
| Usuarios / roles | CRUD | R | R | — |
| Pacientes | CRUD | CRUD | R + crear evolución* | R propio (su reserva) |
| Agenda / turnos | CRUD | CRUD | R/U (sus turnos: confirmar, iniciar, cerrar) | Crear (reserva) + R/U propio por token |
| Bloqueos / sobreturnos | CRUD | CRUD | R (proponer) | — |
| Lista de espera | CRUD | CRUD | R | Anotarse / darse de baja (por token) |
| Ficha clínica / odontograma / evolución | CRUD | R (sin editar clínica) | CRUD (sus pacientes) | R propio |
| Presupuestos / planes | CRUD | CRUD | CRUD | R propio |
| Consentimientos | CRUD | CRUD (gestionar firma) | CRUD | Firmar (por token) |
| Caja / señas / cobros | CRUD + cierres | CRUD (sin reabrir cierres) | R (sus cobros) | Pagar seña (link MP) |
| Liquidaciones OS | CRUD | CRUD | R | — |
| Mensajes / plantillas | CRUD | R + reenviar | — | Recibir (opt-in) |
| Auditoría | R | — | — | — |
| Exportación CSV/JSON | Sí | Parcial (agenda/caja) | Parcial (clínica propia) | — |

\* Recepción nunca edita contenido clínico; Odontólogo nunca reabre cierres de caja.

## Rutas públicas

Sin autenticación (rate-limit + validación estricta):

- `GET /reservar/:tenantSlug` — disponibilidad y formulario de reserva.
- `POST /reservar/:tenantSlug` — crear reserva (nombre + DNI + teléfono).
- `/mis-turnos/:token` — ver / confirmar / cancelar / reprogramar turno propio.
- `/lista-espera/:token` — anotarse / darse de baja.
- `/pagar/:token` — pagar seña (redirige a Mercado Pago).
- `/firmar/:token` — firmar consentimiento.
- `/webhooks/mercadopago` — webhook de pagos (firma HMAC).
- `/webhooks/whatsapp` — webhook entrante WA (verificación + firma).
