# Design

## Context
Ver `proposal.md` y `specs/reserva-publica-pwa/spec.md`.
El backend FastAPI ya expone endpoints públicos para la reserva y autogestión de turnos:
- `GET /api/reservar/:slug`: devuelve el catálogo (prestaciones, profesionales, sillones y slots reales calculados sin solapamientos).
- `POST /api/reservar/:slug`: registra la reserva, paciente y seña si aplica, generando `token_gestion`.
- `GET /api/mis-turnos/:token` y sus acciones `confirmar`, `cancelar`, `reprogramar`.
- `POST /api/clinica/consentimientos/:token/firmar`: firma de consentimientos.

El frontend existente en `src/frontend` cuenta con React 18, TypeScript, TailwindCSS, React Router y TanStack Query. Este diseño formaliza la arquitectura de componentes, manejo de estado, PWA y flujos móviles.

## Goals / Non-Goals

**Goals:**
- Implementar el flujo completo de reserva pública (`/reservar/:slug`) móvil-first con alta conversión y UX fluida.
- Proveer páginas públicas de autogestión para los enlaces compartidos por WhatsApp o email (`/mis-turnos/:token`, `/pagar/:token`, `/firmar/:token`, `/lista-espera/:token`).
- Cumplir estrictamente con las reglas de negocio y gobernanza del proyecto:
  - R5: TypeScript estricto, sin `any`, componentes en `PascalCase`.
  - R6: Ningún dato clínico en `localStorage` (solo almacenamiento volátil en memoria o estado de React).
  - R8: Montos calculados exclusivamente en el servidor; el frontend nunca suma ni recalcula precios.
  - RN-GL-02: Textos y mensajes en español rioplatense claro y cálido.
- Configurar PWA instalable con Service Worker para shell offline.

**Non-Goals:**
- No incluye el panel administrativo interno del odontólogo o secretaria (eso corresponde a C-16 y C-17).
- No incluye autenticación JWT de pacientes (los pacientes operan sin login por medio de tokens opacos seguros).

## Decisions

### 1. Arquitectura de Navegación y Rutas (React Router v6)
- `/reservar/:slug`: Asistente de reserva en 3 pasos:
  1. *Paso 1: ¿Qué necesitas?* (Selección de prestación y profesional opcional).
  2. *Paso 2: ¿Cuándo te viene bien?* (Día en calendario interactivo + grilla de horarios disponibles).
  3. *Paso 3: Tus datos* (Formulario con validación de DNI, teléfono y opt-in WA).
  4. *Paso 4: Confirmación y Seña* (Detalle del turno, link a MP si requiere seña y enlace de gestión personal).
- `/mis-turnos/:token`: Pantalla de consulta del turno con botones de acción (Confirmar, Cancelar con motivo, Reprogramar).
- `/pagar/:token`: Pantalla enfocada en el pago de la seña con Mercado Pago (botón oficial y QR).
- `/firmar/:token`: Visor de consentimiento médico con canvas interactivo para firma manuscrita y botón de confirmación legal.
- `/lista-espera/:token`: Aceptación de hueco en 1 clic.

### 2. Gestión de Estado y Consultas con TanStack Query
- Se utiliza `useQuery` para obtener disponibilidad con caching inteligente y refresco automático al seleccionar día/profesional.
- Se utiliza `useMutation` para `crear_reserva`, `confirmar_turno`, etc., manejando estados de carga y error con mensajes en rioplatense (ej. error 409: *"¡Uh! Ese horario se acaba de ocupar, elegí otro disponible"*).

### 3. PWA y Offline
- Configuración de `vite-plugin-pwa` con `autoUpdate` para asegurar que el paciente siempre reciba la versión más reciente del frontend sin pasos manuales.
- Cache-first para assets estáticos (CSS, JS, iconos), Network-first para llamadas a `/api/`.
- Banner sutil de conexión caída (*"Estás sin internet, pero tus datos están a salvo"*) cuando `navigator.onLine === false`.

## Risks / Trade-offs

- [Riesgo de reserva concurrente (409)] → Mitigación: Detección específica de código HTTP 409 en la mutation; la UI resalta el horario en rojo y recarga automáticamente los slots disponibles del día.
- [Privacidad en dispositivos compartidos] → Mitigación (R6): No se almacena historial ni datos médicos en `localStorage`. El paciente accede a su turno únicamente a través de su token único en la URL.
