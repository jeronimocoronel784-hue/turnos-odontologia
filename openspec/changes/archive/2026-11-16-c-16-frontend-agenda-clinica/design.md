# Design

## Context

Ver `proposal.md` — Why. El estado actual que condiciona el cómo:

- **Frontend**: React 18 + TS 5 + Vite 5 + Tailwind, router de datos (`createBrowserRouter`) con **solo rutas públicas** de C-15 (`/`, `/reservar/:slug`, `/mis-turnos/:token`, `/pagar/:token`, `/firmar/:token`, `/lista-espera/:token`) y un `api-client.ts` de ~30 líneas que solo sabe llamar a `/api/health`. TanStack Query ya está instalado y configurado (`crearQueryClient`), la PWA cachea solo el shell (`globPatterns` estáticos, `navigateFallbackDenylist: [/^\/api\//]`). **No hay runner de tests** (sin vitest ni RTL).
- **Backend (contrato existente, no se modifica)**: `POST /api/auth/login` devuelve `access_token` en el cuerpo **y** setea la cookie `refresh_token` (`HttpOnly`); `POST /api/auth/refresh` rota tokens con la cookie y devuelve un access nuevo; `GET /api/auth/me` devuelve `IdentidadRead` (id, tenant, email, nombre, `roles: list`). La agenda (`GET /api/agenda?desde&hasta&profesional_id&sillon_id&estado`) devuelve **solo IDs** (`TurnoRead`, `BloqueoRead`), sin nombres. Los catálogos necesarios ya existen: `GET /api/usuarios`, `/api/prestaciones`, `/api/sillones`, `/api/tenant/politicas`. La matriz RBAC del backend vive en `src/backend/app/domain/rbac.py` y es la autoridad (403 real).
- **Restricciones del proyecto**: R5 (sin `any`, TS estricto, componentes `PascalCase`), R6/R9 (datos clínicos fuera de `localStorage`, sin PHI en logs/URLs/errores), R8 (montos solo del servidor), R11 (≥2 casos por comportamiento), governance MEDIO.
- **Restricción de entorno conocida**: los routers de `pacientes`, `clinica`, `caja` y `presupuestos` no commitean (ver `proposal.md` — Impact). La UI se puede construir y testear con dobles de `fetch`, pero la verificación de integración de escrituras queda a la espera del fix.

## Goals / Non-Goals

**Goals**

- Un shell interno seguro (sesión sin credenciales persistentes) y reutilizable por C-17 sin redefinirlo.
- Cuatro features verticales (agenda, pacientes, clínica, comunicaciones) que consumen el contrato actual sin tocar el backend.
- Base de tests de frontend (vitest + RTL + jsdom) que permita TDD desde la primera tarea.
- Que la UI degrade bien con el bug de persistencia (mensajes honestos, sin prometer guardado que no ocurrió).

**Non-Goals**

- Caja, obras sociales, administración y dashboards (C-17); PWA pública (C-15, ya cerrada).
- Subida real de archivos clínicos: el backend solo persiste **metadatos** (`storage_key`), así que la UI no implementa upload.
- Tiempo real por WebSocket/SSE: se resuelve con polling acotado, sin cambios backend.
- Modo offline de escritura para la app interna: a diferencia de la reserva pública (US-063), acá se bloquean las mutaciones sin conexión.
- Rediseño visual global / design system: el polish es de C-17; acá se usan los estilos existentes.
- Librería de componentes, de formularios o de gráficos: se evita sumar dependencias de runtime.

## Decisions

### D1 — Sesión: access en memoria + refresh en cookie `HttpOnly`

El access token vive en un módulo (`shared/sesion.ts`) con suscripción a cambios; **nunca** se escribe en `localStorage`/`sessionStorage`. Al recargar, se restaura con `POST /api/auth/refresh` (la cookie viaja sola con `credentials: "include"`). El logout llama a `POST /api/auth/logout` y limpia el `QueryClient`.

- *Alternativas descartadas*: access en `localStorage` (R6/R9: XSS con acceso a datos clínicos y token de 15 min persistido); access en cookie `HttpOnly` (requeriría cambiar el contrato del backend, fuera de alcance); pedir login en cada recarga (rompe la operación real).

### D2 — Protección de rutas con loaders del router de datos

Un layout sin path (`/app`) tiene un `loader` que ejecuta `requerirSesion()`: espera el bootstrap (promesa memoizada, un solo refresh aunque haya varias navegaciones) y, si no hay sesión, lanza `redirect("/login?destino=<ruta>")`. El login lee `destino` y vuelve ahí. La pantalla de login queda fuera del layout protegido.

- *Por qué*: es la forma idiomática de React Router 6.26, evita parpadeo de contenido protegido y permite restaurar el destino sin estado global.
- *Alternativa descartada*: componente `<RequireAuth>` con `useEffect` (renderiza primero y expulsa después: parpadeo y condiciones de carrera con las queries).

### D3 — Cliente HTTP autenticado con refresh *single-flight*

`shared/api-client.ts` gana `apiFetch<T>(ruta, opciones)`:

1. agrega `Authorization: Bearer <access en memoria>` y `credentials: "include"`;
2. si el status es `401` y la ruta no es de auth, espera **un único** refresh compartido y reintenta una sola vez;
3. si el refresh falla, limpia la sesión y notifica al router (redirige a login);
4. si el status no es 2xx, lanza `ErrorApi { status, mensaje }` tomando `detail` del backend (mensajes ya en rioplatense);
5. maneja `204` sin intentar parsear JSON.

- *Por qué*: concentra en un punto las reglas de R9 (no loguear cuerpos ni query strings) y el reintento, que de otro modo se duplica en cada feature.
- *Alternativa descartada*: `axios` con interceptores (dependencia nueva para algo que `fetch` resuelve); refresh por componente (multiplica refreshes y rompe la rotación de tokens).

### D4 — Espejo de RBAC en el cliente, con el backend como autoridad

`shared/rbac.ts` replica la forma del backend (`Recurso`, `Accion`, `permite(roles, recurso, accion)`) con **solo** las filas que usa C-16: `PACIENTES`, `AGENDA`, `BLOQUEOS`, `CLINICA`, `PRESUPUESTOS`, `CONSENTIMIENTOS`, `MENSAJES`. Los guards de ruta, el menú y la visibilidad de acciones se derivan de esa función, no de `if (rol === ...)` dispersos.

- *Por qué*: la matriz es la misma que documenta `knowledge-base/03_actores_y_roles.md`; derivar todo de una función evita que el menú y los botones se contradigan. La agenda del odontólogo arranca filtrada por su propio `profesional_id` y, si consulta turnos de otro profesional, quedan en solo lectura (§03:22 le da lectura/actualización solo sobre sus turnos). Recepción gestiona la firma de consentimientos (§03:27) pero no edita ficha ni odontograma (RN-CL-03).
- *Mitigación de drift*: un test de paridad fija las filas esperadas y un comentario apunta a `domain/rbac.py`; además, cualquier error de espejo se traduce en un `403` real que la UI muestra (nunca se asume permiso).
- *Alternativa descartada*: endpoint que exponga la matriz (cambio backend); checks ad-hoc por pantalla (drift garantizado).

### D5 — Capa de datos con TanStack Query y claves por dominio

`shared/query-keys.ts` define fábricas (`pacientes.lista(q)`, `agenda.rango({desde,hasta,filtros})`, `clinica.ficha(id)`, `odontograma.de(id)`, `mensajes.porTurno(id)`, etc.). Reglas:

- `staleTime` 30 s para listados y 5 min para catálogos (usuarios, prestaciones, sillones, políticas);
- la agenda usa `refetchInterval` de 30 s **solo** con la pestaña visible (`refetchIntervalInBackground: false`) para reflejar confirmaciones de WhatsApp;
- las mutaciones invalidan las claves afectadas (no se recarga la página);
- el cambio de estado de turno usa actualización optimista **con rollback** ante `409/422`.

- *Alternativa descartada*: estado global propio (Redux/Zustand) — TanStack Query ya está y cubre caché + invalidación.

### D6 — Composición de nombres para la agenda (el backend devuelve IDs)

La vista de agenda resuelve nombres con cuatro consultas de catálogo en paralelo (usuarios, prestaciones, sillones, políticas) más la **lista de pacientes del tenant** (`GET /api/pacientes`), con la que se arma un `Map<id, {nombre, dni, telefono}>` en memoria. Si un ID no aparece, se muestra un texto de reemplazo ("Paciente no encontrado") en lugar de un UUID crudo.

- *Por qué*: evitar N+1 (un `GET /api/pacientes/{id}` por turno) y no tocar `AgendaVistaRead`.
- *Límite asumido*: con un padrón grande la lista completa es costosa; se acepta para el piloto (1 consultorio) y se anota como deuda (ver Open Questions).

### D7 — Estructura de features y rutas

```text
src/frontend/src/
  features/auth/            LoginPage, useSesion, api.ts
  features/agenda/          AgendaPage, TurnoForm, TurnoDetalle, ReprogramarDialog, api.ts, queries.ts, tipos.ts
  features/pacientes/       PacientesPage, PacienteDetalle, PacienteForm, api.ts, queries.ts
  features/clinica/         FichaPage, Evoluciones, Odontograma, Adjuntos, Consentimientos, Presupuestos, api.ts, queries.ts
  features/comunicaciones/  MensajesPage, LogMensajes, PlantillasPage, api.ts, queries.ts
  shared/                   api-client.ts, sesion.ts, rbac.ts, query-keys.ts, formatters.ts, componentes de error/estado vacío
```

Rutas: `/login` (pública) y `/app/{agenda,pacientes,pacientes/:id,pacientes/:id/clinica,comunicaciones,comunicaciones/plantillas}`. Las rutas públicas de C-15 y `HomePage` no se tocan. Componentes en `PascalCase`, archivos de lógica en `camelCase`, sin `any` (R5).

### D8 — Odontograma FDI sin librerías

Grilla de botones por cuadrante (permanente 11–48; selector para decidua 51–85, que el backend valida), con las 7 superficies y los 10 eventos del dominio como constantes tipadas espejadas en `features/clinica/odontograma.constantes.ts`. La pieza se pinta con el último evento por superficie; el historial se abre en un panel al seleccionar la pieza. Objetivo táctil ≥ 44 px y superficies como botones grandes en panel inferior (no zonas minúsculas dentro del diente).

- *Alternativa descartada*: SVG dental con `d3`/`react-arc` (dependencia y complejidad para una v1).

### D9 — Consentimiento: texto por defecto editable + firma con nombre y trazo opcional

`ConsentimientoCreate` exige `texto_version` y `texto_contenido` (el backend no tiene endpoint de textos). La UI trae un **texto borrador** versionado (`v1-2026`) en una constante, editable antes de emitir. La firma envía `firmado_por` (nombre de quien firma), `firma_datos` (data URL PNG de un `<canvas>` de trazo libre, o `"firma presencial: <nombre>"` si se firma sin trazo) y `canal: "presencial"`. Pueden emitir y firmar dueño, odontólogo y recepción (matriz §03); el contenido de la ficha y del odontograma sigue restringido al rol clínico.

- *Por qué*: cumple el contrato actual sin inventar endpoints y deja el contenido legal como decisión del PO (ver Open Questions).
- *Cuidado*: el trazo se envía al backend y **no** se guarda en el navegador (R6/R9).

### D10 — Formularios controlados con validadores locales

Sin `react-hook-form`: formularios controlados + validadores puros por feature que replican las restricciones de los schemas (obligatorios, largos máximos, DNI numérico normalizado). La API sigue validando (`422`), y sus mensajes se muestran tal cual.

- *Por qué*: los formularios del alcance son acotados; sumar una librería de forms aumenta superficie sin beneficio claro en este change.

### D11 — Tests con vitest + RTL + jsdom, sin MSW

Se agregan `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event` y `@testing-library/jest-dom` como devDependencies, con `vitest.config.ts` (environment `jsdom`, `setupFiles` con `jest-dom`) y scripts `test`/`test:run`. Los tests montan la feature con `QueryClientProvider` (query client sin reintentos) y `MemoryRouter`, y reemplazan `fetch` con un doble tipado (`vi.stubGlobal`) que valida ruta, método y cuerpo.

- *Por qué*: no hay runner; MSW agrega peso y este change no necesita matching de red complejo.
- *Cobertura mínima*: sesión (login ok/401, refresh single-flight, logout), guards por rol, agenda (bloqueo, sobreturno, cambio de estado con rollback), pacientes (búsqueda, 409), clínica (evolución, odontograma, consentimiento), comunicaciones (log, reenvío) y la regla de "nada en storage".

### D12 — Offline de la app interna: lectura sí, escritura no

Las rutas internas caen al shell cacheado (el `navigateFallback` ya lo cubre) y **no** se cachean respuestas de API. Sin conexión, `BannerOffline` avisa y los formularios de escritura se deshabilitan; las consultas muestran el error de red con reintento manual. No hay cola offline para turnos/HC (a diferencia de la reserva pública): un turno o una evolución encolada sin validación del servidor es un riesgo clínico.

## Risks / Trade-offs

- **[Persistencia rota en `pacientes`/`clinica`/`caja`/`presupuestos`]** → La UI puede mostrar `201` y luego no encontrar el registro. Mitigación: dejar el riesgo escrito en `proposal.md` y en la UI ("si el alta no aparece, avisá al administrador"), tests de UI con `fetch` doble, y **abrir el fix como change aparte (C-19, governance CRÍTICO) antes de la demo/E2E**. No se parchea el backend desde C-16.
- **[Drift entre el RBAC de la UI y `rbac.py`]** → Test de paridad + comentario de referencia; el backend sigue devolviendo `403` y la UI lo muestra en vez de asumir permiso.
- **[Agenda con lista completa de pacientes]** → `staleTime` alto y `Map` en memoria; si el padrón crece, se propone enriquecer `AgendaVistaRead` (change backend posterior).
- **[Polling de 30 s con muchas pestañas abiertas]** → se pausa en segundo plano; el intervalo es configurable en una constante.
- **[Firma en canvas en móvil]** → trazo opcional (la firma con nombre siempre alcanza); controles grandes y botón de limpiar.
- **[Texto de consentimiento borrador]** → marcado como borrador editable y anotado para revisión del PO; no se presenta como texto legal definitivo.
- **[Tests de UI con `fetch` doble pueden divergir del contrato]** → los dobles usan los tipos de `shared/api-types.ts` y los casos borde (`409`, `422`, `403`) se copian de los schemas reales.
- **[`npm run build` es el único gate hoy]** → se suma `test:run` al script de verificación local y al workflow de CI.

## Migration Plan

- **Sin migraciones de base ni cambios de API**: el change es aditivo en el frontend.
- **Orden de despliegue**: (1) devDependencies + configuración de tests; (2) shell (`sesion`, `api-client`, `rbac`, router, login); (3) features en orden agenda → pacientes → clínica → comunicaciones; (4) CI. Cada paso deja `tsc --noEmit` y `test:run` en verde.
- **Rollback**: revertir el commit del change; las rutas de C-15 siguen intactas porque `/app/*` y `/login` son aditivas.
- **Dependencia externa**: el bug de persistencia (C-19) no impide desplegar la UI, pero sí firmar la demo de escrituras. Se documenta en `README.md`/`CHANGES.md` al cerrar.

## Open Questions

- **Texto legal del consentimiento**: el borrador `v1-2026` es contenido de ejemplo; el PO debe validar el texto definitivo y su versión (no cambia el diseño ni las tareas).
- **Padrón grande en la agenda**: ¿conviene un `AgendaVistaRead` enriquecido con nombre de paciente/prestación en el backend? Se puede responder después del piloto sin alterar este diseño.
