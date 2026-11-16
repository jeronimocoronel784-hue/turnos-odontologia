# Proposal

## Why

El backend ya expone todo lo que la operación diaria necesita (agenda, pacientes, HC/odontograma, consentimientos, presupuestos y comunicaciones), pero **no existe la PWA interna**: hoy recepción y odontólogo solo pueden operar pegándole a Swagger o a `curl` con un token a mano. La PWA pública de C-15 cubre al paciente y queda huérfana del otro lado del mostrador, y C-17 (`frontend-caja-os-admin`) no puede arrancar sin un shell interno con login, sesión y guards por rol que hoy no existe.

## What Changes

- **Shell interno autenticado (nuevo)**: login de staff contra `POST /api/auth/login`, sesión con access token **en memoria** + refresh en cookie `HttpOnly` (bootstrap con `POST /api/auth/refresh`, logout con `POST /api/auth/logout`), guards de ruta por rol espejando la matriz de `03_actores_y_roles.md`, layout con navegación y tratamiento explícito de `401` (sesión vencida → login) y `403` (sin permiso → mensaje rioplatense).
- **Agenda operativa**: vista día/semana por profesional y sillón con duraciones reales, estados del turno, bloqueos no reservables, sobreturnos marcados, alta de turno, cambio de estado (presente/ausente/cancelado/finalizado) y reprogramación en 1 clic con historial; refresco automático para reflejar confirmaciones de WhatsApp (US-001, Flujo 2).
- **Pacientes**: búsqueda por nombre/DNI/teléfono, alta con ficha clínica 1:1, edición de contacto, opt-in/baja de WhatsApp y baja lógica (§03 matriz de pacientes), más el acceso directo a la HC del paciente.
- **Clínica**: anamnesis/ficha, evoluciones append-only (con corrección aditiva), odontograma FDI interactivo por pieza/superficie con historial y adjuntos, presupuestos del plan y consentimientos (alta, firma en el acto y revocación) (US-020/021/022/023, Flujo 3).
- **Comunicaciones**: log de mensajes por turno con estado e intentos, reenvío manual y edición de plantillas (recepción: leer/reenviar; dueño: CRUD) (US-010).
- **Política de cancelación visible**: la UI muestra anticipación mínima y horas de cancelación desde `GET /api/tenant/politicas` y las usa para avisar antes de cancelar/reprogramar (US-011).
- **Infraestructura de tests de frontend (nuevo)**: no hay runner hoy; se agregan `vitest` + `@testing-library/react` + `jsdom` y scripts `test`/`test:run`, con tests de guards, agenda (bloqueos/sobreturnos) y odontograma por pieza/superficie.
- **`CHANGES.md`**: se actualiza la entrada C-16 con la división en dos capabilities y la dependencia del fix de persistencia.

Ningún cambio es **BREAKING**: no se modifica el contrato de la API ni las rutas públicas existentes.

## Capabilities

### New Capabilities
- `frontend-shell-interno`: sesión de staff en la PWA interna — login/logout, bootstrap por refresh cookie, access token en memoria, restauración tras recarga, guards por rol, layout/navegación y manejo de `401`/`403`.
- `frontend-agenda-clinica`: pantallas internas de agenda (turnos, estados, bloqueos, sobreturnos, reprogramación), pacientes, clínica (ficha, evoluciones, odontograma FDI, adjuntos, presupuestos, consentimientos) y comunicaciones (log por turno, reenvío, plantillas).

### Modified Capabilities
<!-- Ninguna: C-16 consume los endpoints ya especificados en agenda-turnos, pacientes, historia-clinica-odontograma, presupuestos-planes y comunicaciones-mensajeria; no cambia el comportamiento del backend ni de la PWA pública. -->

## Impact

- **Frontend (afectado)**: `src/frontend/src/main.tsx` (router con rutas internas protegidas y públicas de C-15), `src/frontend/src/shared/api-client.ts` (cliente autenticado: `credentials: "include"`, retry único tras refresh, mapeo de errores), nuevos `shared/sesion.ts` y `shared/rbac.ts`, nuevos `features/auth`, `features/agenda`, `features/pacientes`, `features/clinica`, `features/comunicaciones`; `package.json` (+devDependencies de test) y configuración de vitest.
- **Backend / API**: **sin cambios**. Se consumen endpoints existentes: `POST /api/auth/login|refresh|logout`, `GET /api/auth/me`; `GET /api/agenda`, `POST /api/turnos`, `PATCH /api/turnos/{id}/estado`, `POST /api/turnos/{id}/reprogramar`, `GET|POST|DELETE /api/bloqueos`; `GET|POST|PATCH|DELETE /api/pacientes` y `PATCH /api/pacientes/{id}/optin`; `GET|PUT /api/pacientes/{id}/ficha`, `GET|POST /api/pacientes/{id}/evoluciones`, `GET|POST /api/pacientes/{id}/adjuntos`, `GET /api/odontograma/{id}`, `POST /api/odontograma/{id}/eventos`, `GET /api/odontograma/{id}/piezas/{pieza}/historial`, `GET|POST /api/consentimientos` y `POST /api/consentimientos/{id}/firmar|revocar`; `GET|POST /api/presupuestos`, `POST /api/presupuestos/{id}/items|presentar|aceptar|rechazar|finalizar` y `GET|POST /api/presupuestos/{id}/turnos`; `GET /api/mensajes`, `POST /api/mensajes/{id}/reenviar`, `GET|POST /api/plantillas` (el alta crea una versión nueva); `GET /api/prestaciones`, `GET /api/sillones`, `GET /api/usuarios`, `GET /api/tenant/politicas`.
- **Riesgo / dependencia bloqueante (detectada, fuera de alcance)**: los routers de `pacientes`, `clinica`, `caja` y `presupuestos` **no llaman a `session.commit()`** (0 ocurrencias; `deps.sesion_db` cierra sin commit). Verificado contra PostgreSQL real: `POST /api/pacientes` → `201` con `0` filas, mismo DNI → `201` en vez de `409`, `POST .../evoluciones` → `201` y `0` filas. La UI puede construirse y testearse, pero **las altas/ediciones de pacientes y HC no van a persistir** hasta que se corrija. No se mezcla ese fix backend (governance CRÍTICO) en C-16 (governance MEDIO, frontend): se recomienda abrir un change aparte (C-19) antes de la demo/E2E. `agenda`, `auth`, `usuarios`, `admin_catalogo`, `comunicaciones`, `lista_espera`, `liquidaciones`, `reserva_publica` y webhooks **sí** commitean.
- **Datos y privacidad**: el access token vive solo en memoria y el refresh en cookie `HttpOnly`; **nunca** se guardan HC, odontograma, DNI ni teléfonos en `localStorage`/`sessionStorage` (R6, R9). Las queries de TanStack Query para datos clínicos no se persisten en disco. Montos y coberturas siempre se muestran tal como los devuelve el servidor (R8).
- **Tests**: unidad/componente con vitest + RTL (mínimo 2 casos por comportamiento: happy path + borde); la verificación de integración real queda condicionada al fix del bug de persistencia.
- **Exclusiones**: sin pantallas de caja, obras sociales, admin ni dashboards (C-17); sin cambios en la PWA pública de C-15; sin lógica de negocio, migraciones, seeds ni endpoints backend nuevos; sin CORS (mismo origen vía proxy de Vite en dev y nginx en la demo).
