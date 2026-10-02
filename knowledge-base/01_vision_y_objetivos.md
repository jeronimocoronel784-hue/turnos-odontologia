# Visión y Objetivos

## Propósito del sistema

Brindar a consultorios y clínicas odontológicas argentinas un SaaS multi-tenant que unifica agenda, historia clínica/odontograma, cobros con obra social y comunicación por WhatsApp en una sola herramienta.

Hoy esos consultorios gestionan agenda, HC, cobros/OS y comunicación con herramientas desconectadas — WhatsApp manual, papel/Excel, software legado desktop o SaaS extranjero sin OS/AFIP/Mercado Pago — lo que genera dobles reservas, ausentismo sin recupero, huecos sin rellenar, doble carga administrativa y pérdida de trazabilidad clínica y financiera. Este sistema elimina esa fragmentación: cada turno nace con su profesional, sillón, duración, cobertura y estado de pago, y cada atención deja registro clínico y movimiento de caja trazables.

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|---|---|---|
| Paciente | Reservar/reprogramar online sin llamar, 24/7 | Confirmar por WhatsApp en 1 toque; pagar seña online; firmar consentimiento desde el celular |
| Recepción / Admin | Ocupar cada hueco de agenda sin solapamientos ni llamadas manuales | Confirmar turnos automáticamente; cobrar y cerrar caja diaria; derivar lista de espera |
| Odontólogo | Registrar HC/odontograma/evolución en la misma cita sin duplicar carga | Presupuestar planes de tratamiento vinculados a citas; indicar controles |
| Dueño / Administrador | Ver rentabilidad por profesional/sillón/OS y auditar todo | Configurar prestaciones, precios, OS y roles; liquidar OS sin planilla; exportar datos |

## Alcance v1.0

- Agenda diaria/semanal multi-profesional + multi-sillón/box con duraciones por prestación, bloqueos y prevención de solapamientos; sobreturnos explícitos; reprogramación con historial.
- Reserva online 24/7 (link público + embed web) sin registro obligatorio (nombre + DNI + teléfono); confirmación/cancelación/reprogramación por el paciente; lista de espera básica con aviso de huecos.
- Recordatorios y confirmación automática por WhatsApp (Business API oficial) + email, con plantillas, opt-in y log auditable; política de cancelación configurable.
- Ficha clínica + anamnesis + odontograma FDI funcional (por pieza/superficie, con historial) + adjuntos (RX/fotos/PDF) + presupuestos/planes de tratamiento vinculados a citas.
- Caja diaria (cobros/gastos, medios, cierre), señas vinculadas a turno, Mercado Pago (link/QR conciliado), cálculo cobertura OS vs particular y liquidación básica exportable.
- Roles y permisos (Dueño, Recepción, Odontólogo; Paciente como actor público), multi-sucursal elemental, auditoría append-only, exportación CSV/JSON, consentimiento informado con firma.
- PWA instalable (móvil + desktop) + web responsive; JWT con access+refresh y rotación.

## Fuera de alcance

- Facturación electrónica AFIP/ARCA nativa completa (v1: exportación conciliable; conector fiscal en v2).
- Periodontograma avanzado, ortodoncia/endodoncia/cirugía profundas, imágenes con IA diagnóstica, dictado por voz o transcripción.
- Recepcionista IA por voz 24/7, campañas de recupero con scoring, marketing automation.
- Stock/inventario, laboratorio protésico, comisiones complejas, consolidación multi-cadena, APIs públicas/marketplace, Google Calendar bidireccional, radiología directa (PACS/sensores).
- App nativa (iOS/Android) obligatoria; push notifications en v1; portal paciente avanzado con pagos recurrentes o telemedicina.

## Métricas de éxito

- Ausentismo: % de turnos en estado `ausente` sobre agendados, por mes y profesional (meta: bajar vs línea de base del piloto).
- Ocupación: % de slots reservados sobre slots ofrecidos, por sillón/semana.
- Recupero: % de huecos por cancelación rellenados vía lista de espera.
- Cobro: % de señas cobradas sobre señas exigibles; días de cierre de caja sin descuadre.
- Adopción: consultorios que completan onboarding en ≤ 1 día; reservas online sobre reservas totales.
- Confianza: 100% de prestaciones invasivas con consentimiento firmado previo; 100% de cambios críticos auditados.
