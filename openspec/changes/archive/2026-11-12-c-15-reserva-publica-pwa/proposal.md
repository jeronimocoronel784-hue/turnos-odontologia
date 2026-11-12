# Proposal

## Why
Actualmente el backend expone los endpoints de reserva pública (`/api/reservar/:slug`), autogestión de turnos (`/api/mis-turnos/:token`), pagos y consentimientos, pero no existe una interfaz gráfica para los pacientes. La reserva online 24/7 sin fricción (Flujo 1, US-002) es el pilar central del consultorio: los pacientes necesitan poder agendar una cita desde su teléfono celular, elegir profesional o prestación, pagar la seña correspondiente y autogestionar su turno de forma accesible y offline-resiliente.

## What Changes
- **PWA Pública Móvil-First (`/reservar/:slug`)**:
  - Selector interactivo de prestación (duración, precio, requerimiento de seña y copago estimado).
  - Selector de profesional (o "Cualquier profesional disponible") y sillón.
  - Calendario y selector de franjas horarias (slots reales disponibles sin solapamientos ni bloqueos).
  - Formulario de datos personales del paciente (nombre, DNI argentino, teléfono, email, fecha de nacimiento, obra social opcional y número de afiliado, con checkbox de consentimiento opt-in para WhatsApp).
  - Integración visual del pago de seña (Mercado Pago link / QR) cuando la prestación lo exige.
- **Páginas Públicas de Autogestión por Token Opaco**:
  - `/mis-turnos/:token`: Visualización del turno propio, estado en tiempo real, confirmación en 1 clic, cancelación con motivo y reprogramación según políticas.
  - `/pagar/:token`: Pantalla de pago directo de seña pendiente con redirección o QR de Mercado Pago.
  - `/lista-espera/:token`: Aceptación en 1 clic de hueco liberado (Flujo 6).
  - `/firmar/:token`: Visualización de consentimiento informado y captura de firma digital con hash SHA-256.
- **PWA & Capacidades Offline**:
  - Manifest Web (`manifest.webmanifest`) instalable en móviles Android / iOS.
  - Service Worker con Vite PWA para shell offline (la aplicación carga instantáneamente sin conexión).
  - Cola offline (`offlineQueue`) con TanStack Query y almacenamiento seguro en memoria/IndexedDB (respetando R6: prohibido almacenar datos clínicos en localStorage).
  - Mensajes de error y estado en español rioplatense amigable (RN-GL-02).

## Capabilities

### New Capabilities
- `reserva-publica-pwa`: Interfaz pública PWA del paciente para reserva online de citas, pago de señas, autogestión por token y soporte offline.

### Modified Capabilities
<!-- No se modifican requisitos normativos de los specs del backend -->

## Impact
- **Frontend**:
  - Nuevas rutas en React Router (`/reservar/:slug`, `/mis-turnos/:token`, `/pagar/:token`, `/lista-espera/:token`, `/firmar/:token`).
  - Nuevos componentes en `src/frontend/src/features/reserva-publica/` y `src/frontend/src/features/autogestion/`.
  - Configuración ampliada de PWA y Service Worker en `src/frontend/src/shared/pwa/`.
  - Clientes API tipados con TypeScript estricto (R5: sin `any`) contra `apiturnos.ismasaleme.me`.
- **Backend / Infraestructura**:
  - Ningún breaking change en la API existente (consume los endpoints de C-06, C-07, C-09, C-11, C-12).
