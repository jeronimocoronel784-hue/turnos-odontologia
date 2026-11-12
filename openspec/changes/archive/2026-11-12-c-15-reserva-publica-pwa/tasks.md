# Tasks

## 1. Tipos y Cliente API de Reserva Pública

- [x] 1.1 Definir interfaces TypeScript estrictas (sin `any`) para el catálogo público, paciente, turno y respuestas de error en `src/frontend/src/shared/api-types.ts`.
- [x] 1.2 Implementar funciones del cliente HTTP (`obtenerDisponibilidadPublica`, `crearReservaPublica`, `obtenerMiTurno`, `confirmarTurno`, `cancelarTurno`, `reprogramarTurno`, `firmarConsentimiento`) en `src/frontend/src/shared/reserva-api.ts` con manejo de errores en rioplatense.
- [x] 1.3 Crear utilidades de formateo para fecha/hora local y moneda argentina (ARS) sin cálculo de montos en cliente en `src/frontend/src/shared/formatters.ts`.

## 2. Flujo de Reserva Online (`/reservar/:slug`)

- [x] 2.1 Implementar `SelectorPrestacion.tsx` para elegir tratamiento, visualizando duración, arancel y aviso si requiere seña.
- [x] 2.2 Implementar `SelectorHorario.tsx` con calendario interactivo y franjas horarias libres obtenidas dinámicamente de la API.
- [x] 2.3 Implementar `FormularioPaciente.tsx` con campos para nombre, DNI, teléfono, email opcional, obra social y checkbox obligatorio de opt-in WhatsApp.
- [x] 2.4 Implementar `ReservaPage.tsx` integrando el asistente por pasos, gestionando errores de solapamiento concurrente (409) con recarga de slots.
- [x] 2.5 Implementar `ConfirmacionReserva.tsx` que muestre el resumen del turno, el `token_gestion` y el botón de Mercado Pago si requiere seña.

## 3. Autogestión de Turnos por Token Opaco

- [x] 3.1 Implementar `MiTurnoPage.tsx` (`/mis-turnos/:token`) con detalle de la cita y acciones de Confirmar, Cancelar con motivo y Reprogramar.
- [x] 3.2 Implementar `PagarSenaPage.tsx` (`/pagar/:token`) con información del turno y enlace/botón oficial de pago de Mercado Pago.
- [x] 3.3 Implementar `FirmarConsentimientoPage.tsx` (`/firmar/:token`) con visor de consentimiento informado y componente de firma digital con canvas táctil.
- [x] 3.4 Implementar `AceptarHuecoPage.tsx` (`/lista-espera/:token`) para confirmación inmediata de hueco liberado en lista de espera.

## 4. Enrutamiento, PWA y Verificación

- [x] 4.1 Configurar las nuevas rutas públicas en `src/frontend/src/main.tsx` con React Router v6.
- [x] 4.2 Implementar `BannerOffline.tsx` para notificar al usuario de forma amigable cuando se pierda la conexión a internet.
- [x] 4.3 Ejecutar verificación de tipos TypeScript (`tsc --noEmit`) y build de Vite (`npm run build`) comprobando que no existan errores de compilación ni advertencias.
