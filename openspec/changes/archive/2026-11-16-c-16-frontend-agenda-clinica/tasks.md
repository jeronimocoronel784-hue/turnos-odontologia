# Tasks

> TDD estricto por tarea: **RED** (test que falla) → **GREEN** (mínimo código) → **TRIANGULATE** (≥2 casos por comportamiento, R11) → **REFACTOR**. Cada tarea se considera hecha solo con su verificación en verde y `tsc --noEmit` limpio. Gobernanza MEDIO: sin cambios en backend, migraciones ni seeds.

## 1. Infraestructura de tests y base compartida

- [x] 1.1 Agregar devDependencies de test (`vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`) y scripts `test`/`test:run` en `src/frontend/package.json`; verificar con `npm install` y `npm run test:run`.
- [x] 1.2 Crear `vitest.config.ts` + `src/frontend/test/setup.ts` (jest-dom) y un test smoke que renderice un componente trivial; verificar que `npm run test:run` ejecuta 1 test en verde.
- [x] 1.3 Crear helper `src/frontend/test/render.tsx` (QueryClient sin reintentos + `MemoryRouter` opcional) y un `fetch` doble tipado con validación de ruta/método/cuerpo; verificar con un test que cubra respuesta `200` y `409`.
- [x] 1.4 Definir los tipos de contrato en `src/frontend/src/shared/api-types.ts` (auth, agenda, pacientes, clínica, comunicaciones, catálogo, políticas) sin `any`; verificar con `npm run build` (`tsc --noEmit`) en verde.
- [x] 1.5 Extender `src/frontend/src/shared/formatters.ts` (fecha/hora en es-AR, rango horario, duración en minutos, normalización de DNI para mostrar) con tests de 2 casos por función (valor típico + borde).
- [x] 1.6 Documentar en `README.md` la sección "Tests de frontend" (`npm install`, `npm run test:run`, `npm run build`) y verificar corriendo los tres comandos tal como quedan escritos.

## 2. Shell interno (sesión, RBAC, navegación)

- [x] 2.1 Implementar `src/frontend/src/shared/sesion.ts`: access en memoria, bootstrap memoizado por `POST /api/auth/refresh`, suscripción a cambios y limpieza de sesión; tests: refresh `200` restaura identidad, refresh `401` deja sin sesión, dos bootstraps simultáneos hacen un solo request y no se escribe nada en `localStorage`/`sessionStorage`.
- [x] 2.2 Implementar `apiFetch` en `src/frontend/src/shared/api-client.ts` (Bearer desde memoria, `credentials: "include"`, `401` → refresh único → reintento, `204` sin parseo, `ErrorApi` con `detail`); tests: reintento exitoso tras `401`, segundo `401` limpia sesión, `403` propaga mensaje y `204` no rompe.
- [x] 2.3 Implementar `src/frontend/src/shared/rbac.ts` con las filas de `PACIENTES`, `AGENDA`, `BLOQUEOS`, `CLINICA`, `PRESUPUESTOS`, `CONSENTIMIENTOS` y `MENSAJES`; tests: paridad con las filas esperadas de `knowledge-base/03_actores_y_roles.md` y denegación por defecto con rol desconocido.
- [x] 2.4 Implementar `features/auth/LoginPage.tsx` (email/password, mostrar errores, redirigir a `destino` o agenda); tests: login `200` navega, `401` muestra mensaje genérico sin revelar el email, `429` pide esperar, formulario vacío no llama a la API.
- [x] 2.5 Proteger `/app` con loader de React Router (`requerirSesion`) y redirección a `/login?destino=...`; tests: sin sesión redirige, con sesión renderiza el layout y tras login vuelve a la ruta pedida.
- [x] 2.6 Implementar layout interno y navegación filtrada por rol con identidad y logout; tests: recepción no ve "Clínica" como editable/odontólogo no ve alta de pacientes, logout llama a `/api/auth/logout` y limpia la caché.
- [x] 2.7 Implementar componentes compartidos de error/estado vacío (`ErrorApi` → mensaje rioplatense con qué pasó, por qué y cómo seguir) y aplicarlos en login/layout; tests: `403`, `404` y `5xx` muestran mensajes distintos, un recurso de otro consultorio no revela datos y nunca se muestra un stack trace.
- [x] 2.8 Cablear las rutas nuevas en `src/frontend/src/main.tsx` sin tocar las públicas de C-15; test de smoke: `/reservar/:slug` y `/mis-turnos/:token` siguen resolviendo, `/app/agenda` redirige a login sin sesión.

## 3. Agenda

- [x] 3.1 Crear `features/agenda/api.ts` y `queries.ts` (agenda por rango, catálogos, políticas, mapa de pacientes) con claves en `shared/query-keys.ts`; tests: arma la URL con `desde`/`hasta`/filtros y no consulta con rango inválido.
- [x] 3.2 Implementar `AgendaPage` con vistas día/semana, navegación de fechas y filtros por profesional/sillón/estado, con la agenda del odontólogo filtrada por su propio profesional y los turnos ajenos en solo lectura; tests: cambio de día conserva filtros, filtros combinados filtran la vista, agenda vacía muestra estado vacío y el odontólogo no ve acciones sobre turnos de otro profesional.
- [x] 3.3 Renderizar turnos, bloqueos y sobreturnos con estados diferenciados y marca de "seña pendiente" cuando corresponde; tests: los 6 estados tienen etiqueta textual, el bloqueo no permite alta encima, el sobreturno se marca aunque comparta franja y la seña pendiente es visible sin calcular montos.
- [x] 3.4 Implementar alta de turno (paciente, profesional, sillón, prestación, inicio y fin sugerido por duración), con override de duración marcado y motivo, y sobreturno explícito que exige motivo; tests: alta `201` aparece en la agenda, `409` por solapamiento no agrega el turno, faltantes u override/sobreturno sin motivo no llaman a la API.
- [x] 3.5 Implementar cambio de estado dentro del grafo (confirmar, presente, finalizado, ausente, cancelar con motivo) con optimista + rollback, y manejo de los `409` de seña impaga y de consentimiento faltante; tests: `200` actualiza estado, `409` de seña no confirma, `409` de consentimiento ofrece firmar, cancela sin motivo no se envía y las acciones fuera del grafo no se ofrecen.
- [x] 3.6 Implementar reprogramación y vista de historial por cadena de `turno_origen_id`; tests: `201` muestra el turno nuevo, `409` conserva la selección y el historial recorre la cadena.
- [x] 3.7 Implementar el refresco de agenda para confirmaciones de WhatsApp (30 s visible, pausado en segundo plano); tests con fake timers: refresca al vencer el intervalo y no lo hace con la pestaña oculta.
- [x] 3.8 Mostrar la política de cancelación (`GET /api/tenant/politicas`) y advertir cuando la acción cae fuera de plazo; tests: muestra anticipación/horas, advierte dentro del plazo y no bloquea si la consulta falla.

## 4. Pacientes

- [x] 4.1 Crear `features/pacientes/api.ts` y `queries.ts` con búsqueda por `q`, DNI y teléfono; tests: búsqueda consulta `/api/pacientes?q=…`, sin resultados ofrece alta y el término no se refleja en la URL.
- [x] 4.2 Implementar alta de paciente con ficha y manejo de `409` por DNI duplicado, incluido el acceso desde la agenda conservando el borrador de turno; tests: `201` abre el detalle, `409` ofrece abrir el existente y faltantes no llaman a la API.
- [x] 4.3 Implementar detalle, edición, opt-in de WhatsApp y baja lógica; tests: `PATCH` de contacto actualiza la vista, opt-in alterna y avisa la consecuencia, baja deja al paciente inactivo y fuera de la búsqueda por defecto.

## 5. Clínica

- [x] 5.1 Implementar ficha clínica y evoluciones (alta, corrección aditiva, sin edición/borrado) con guards de rol; tests: recepción lee sin acciones de edición, odontólogo guarda anamnesis y una corrección referencia a la evolución original.
- [x] 5.2 Implementar `Odontograma` FDI (permanente y decidua, 7 superficies, 10 eventos) con historial por pieza; tests: render por cuadrante, alta de evento repinta la pieza, historial cronológico y pieza inválida no se envía.
- [x] 5.3 Implementar adjuntos clínicos (metadatos + asociación a evolución/evento); tests: alta `201` aparece en el listado, metadatos incompletos no llaman a la API y nada se guarda en `localStorage`/`sessionStorage`.
- [x] 5.4 Implementar consentimientos (alta con texto borrador `v1-2026` editable, firma con nombre y trazo opcional en canvas, revocación con motivo) disponibles para dueño, odontólogo y recepción; tests: alta `201` muestra versión, firma `200` muestra firmado por/fecha, recepción puede firmar pero no editar la ficha, revocar sin motivo no envía, tras revocar `presente` vuelve a bloquear y el rechazo del backend recarga el estado real.
- [x] 5.5 Implementar presupuestos del plan (listado con totales del servidor, alta con prestación/pieza/cantidad, transiciones presentar/aceptar/rechazar/finalizar y vínculo de turnos); tests: no recalcula importes en el cliente, alta `201` refresca totales, `409` al aceptar con invasiva sin consentimiento ofrece firmar, presupuesto sin cobertura muestra a cargo igual al total, el vínculo de un turno refleja `en_curso` y pieza FDI inválida no se envía.

## 6. Comunicaciones

- [x] 6.1 Implementar el log de mensajes por turno y por paciente (`GET /api/mensajes`) con estado, intentos, programado y cuerpo; tests: lista los mensajes del turno, estado vacío explica el opt-in y error del proveedor se muestra sanitizado.
- [x] 6.2 Implementar reenvío manual y el caso de paciente sin opt-in; tests: reenvío agrega mensaje pendiente, sin opt-in advierte y no marca como enviado y el fallo de la API deja el mensaje reenviable.
- [x] 6.3 Implementar plantillas: lectura para recepción, nueva versión para dueño, versión conservada en el log; tests: recepción no ve acciones, dueño crea versión incrementada y un mensaje viejo conserva su versión.

## 7. Verificación de integración y cierre

- [x] 7.1 Ejecutar `npm run build` y `npm run test:run` en `src/frontend` y corregir lo que aparezca; verificar ambos en verde y dejar la salida registrada en el resumen del apply.
- [x] 7.2 Verificación manual contra la API real (Postgres desechable `127.0.0.1:5433`, usuarios demo): login, carga de agenda, alta de turno y cambio de estado; verificar que el `POST /api/turnos` aparece al refrescar y documentar como bloqueado lo que dependa del bug de persistencia (pacientes/HC) con referencia al change C-19.
- [x] 7.3 Actualizar `CHANGES.md` (estado de C-16, las dos capabilities nuevas y la dependencia del fix de persistencia) y verificar que la entrada quede consistente con `openspec list --specs`.
- [x] 7.4 Agregar el paso de tests de frontend al workflow de CI (`.github/workflows/ci.yml`) y verificar que el YAML quede válido y que el paso corra `npm ci && npm run test:run` en `src/frontend`.
