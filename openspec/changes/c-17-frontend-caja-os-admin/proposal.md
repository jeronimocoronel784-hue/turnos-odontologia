# Proposal

## Why

C-16 cubre la operación clínica del día (agenda, pacientes, HC, comunicaciones), pero **el dinero y la configuración del consultorio siguen sin pantalla**: hoy recepción cobra pegándole a `curl`, el dueño no puede cerrar la caja ni liquidar una obra social, y la configuración del tenant (prestaciones, precios, sillones, políticas, usuarios) se edita a mano contra Swagger. El backend ya tiene todos esos endpoints implementados y testeados (C-04, C-11, C-13), así que el costo de cerrar el producto es enteramente de frontend.

C-17 es el último eslabón del roadmap: entrega la operación administrativa sobre el shell que instala C-16 y hace el **polish visual final** del producto para la demo. Sin C-17, el consultorio no puede cuadrar la caja del día, facturar a una obra social ni configurar sus precios desde la aplicación.

## What Changes

- **Caja diaria (US-030, Flujo 4)**: movimientos por medio de pago (ingreso/egreso), apertura de cierre por fecha, cierre con `total_contado` y **diferencia visible**, cierre cerrado inmutable y **reapertura solo Dueño con motivo**; cobro del saldo de una atención usando el cálculo del servidor (`GET /api/caja/turnos/{id}/liquidacion` → `POST .../cobrar`) y gestión de señas (listar, cobrar, resolver cancelación, vencer).
- **Obras sociales (US-040/041, Flujo 5)**: consulta de cobertura al agendar (precio particular, cobertura, a cargo, arancel vencido con advertencia), liquidaciones por OS/período con estados (`borrador → presentada → pagada|con_debitos|anulada`), **débitos con motivo obligatorio**, cierre, resultado, anulación con motivo y **exportación CSV/JSON generada en el servidor**.
- **Administración del tenant (US-050)**: ABM de prestaciones (duración, precio, seña, invasiva, activa), sillones con `sucursal`, padrón de coberturas OS, políticas del consultorio (anticipación, seña por defecto, horas de cancelación) y usuarios con cambio de rol (matrícula obligatoria para odontólogo).
- **Panel del consultorio**: tablero del día con **valores agregados por el servidor** (cierre abierto/cerrado del día, liquidaciones en borrador/presentadas, señas pendientes/vencidas, turnos de hoy por estado), sin recalcular dinero en el cliente.
- **Polish visual final**: tokens de diseño unificados, estados de carga/vacío/error en rioplatense sobre todas las pantallas internas, responsive verificado a 360 px sin scroll horizontal y foco visible por teclado.
- **Tests de frontend**: se extiende la base de vitest + RTL que instala C-16 con los casos de caja, OS, admin y paridad de RBAC ampliada.

Ningún cambio es **BREAKING**: no se modifica el contrato de la API, ni las rutas públicas de C-15, ni las pantallas de C-16.

## Capabilities

### New Capabilities
- `frontend-caja-os`: pantallas internas de caja (movimientos, apertura/cierre/reversión de cierre, cobro de atención, señas) y de obras sociales (cobertura al agendar, liquidaciones con débitos, exportación CSV/JSON), respetando que los montos los calcula siempre el servidor y que el cierre cerrado es inmutable.
- `frontend-admin-tenant`: pantallas internas de administración del consultorio (prestaciones, sillones/sucursal, padrón de coberturas, políticas, usuarios y roles), panel del consultorio con datos del servidor y la capa de consistencia visual/estados que cierra el producto.

### Modified Capabilities
<!-- Ninguna: C-17 consume endpoints ya especificados en caja-senas, obras-sociales-liquidacion, catalogo-configuracion y auth-rbac-tokens. No cambia comportamiento del backend ni de la PWA pública. -->

## Impact

- **Frontend (afectado)**: se suman `features/caja` (movimientos, cierre, cobro, señas), `features/os` (cobertura, padrón, liquidaciones, export), `features/admin` (prestaciones, sillones, políticas, usuarios), `features/panel` (tablero del día) y `shared/` gana tipos de contrato de caja/OS/admin, `formattersMonto`, componentes de tabla/estado y tokens de diseño. Se **reutiliza** el shell de C-16 (`shared/sesion.ts`, `apiFetch`, `shared/rbac.ts`, layout y guards): C-17 no lo reimplementa, lo extiende con `CAJA`, `LIQUIDACIONES`, `CONFIGURACION`, `USUARIOS` y las acciones `REABRIR_CIERRE` / `EXPORTAR`.
- **Backend / API**: **sin cambios**. Endpoints consumidos, todos existentes: `GET|POST /api/caja/movimientos`, `GET|POST /api/caja/cierre`, `GET /api/caja/cierre/{id}`, `POST /api/caja/cierre/{id}/cerrar`, `POST /api/caja/cierre/{id}/reabrir`, `GET /api/caja/turnos/{id}/liquidacion`, `POST /api/caja/turnos/{id}/cobrar`; `GET|POST /api/senas`, `GET /api/senas/{id}`, `POST /api/senas/{id}/cobrar|cancelacion|vencer`; `GET /api/os/cobertura`, `GET|POST /api/liquidaciones`, `GET|PATCH|DELETE /api/liquidaciones/{id}`, `POST /api/liquidaciones/{id}/cerrar|resultado`, `GET /api/liquidaciones/{id}/exportar?formato=csv|json`; `GET|POST|PATCH|DELETE /api/prestaciones`, `GET|POST|PATCH|DELETE /api/sillones`, `GET|POST|PATCH|DELETE /api/coberturas`, `GET|PATCH /api/tenant/politicas`; `GET|POST /api/usuarios`, `PATCH /api/usuarios/{id}/rol`; catálogos de lectura ya usados por C-16.
- **Dependencia de ejecución (bloqueante, no de diseño)**: C-17 reutiliza el shell de C-16. Con C-16 en **0/37 tareas**, aplicar C-17 primero obligaría a implementar sesión, `apiFetch`, RBAC y layout dentro de este change. El orden correcto es C-16 → C-17; el apply de C-17 queda bloqueado hasta que el shell exista.
- **Riesgo / dependencia bloqueante detectada (fuera de alcance)**: `src/backend/app/api/routers/caja.py` **no llama a `session.commit()`** (0 ocurrencias, igual que `pacientes`, `clinica` y `presupuestos`). Verificado por inspección: movimiento, apertura de cierre, cierre, reapertura, cobro de turno y señas responden `2xx` y no persisten. **Toda la caja de C-17 queda inservible hasta que se corrija**: se recomienda abrir el change C-19 (fix de commits, governance CRÍTICO) antes del apply. `liquidaciones`, `admin_catalogo` y `usuarios` **sí** commitean.
- **Alcance diferido a C-14 (no entregable acá)**: auditoría consultable (`GET /api/auditoria`), exportación 1-clic de agenda/pacientes/caja, exportación de datos del paciente y página legal pública **no tienen endpoint** en el backend (no existe router de auditoría ni de exportación). Aunque `CHANGES.md` los agrupa en C-17, corresponden a C-14 `auditoria-exportacion`, que sigue pendiente: se excluyen y la UI de auditoría se suma cuando C-14 aterrice, sin rehacer el shell. También queda afuera la **importación Excel** (US-063) porque requiere un endpoint de importación inexistente.
- **Datos y privacidad**: ningún monto se calcula en el cliente (R8); las exportaciones se descargan tal como las arma el servidor y no se guardan en el navegador; usuarios nunca exponen hash de contraseña (R9); nada de caja/OS en `localStorage`/`sessionStorage` (R6).
- **Tests**: mínimos de R11 por comportamiento (happy path + borde) con vitest + RTL sobre los dobles de `fetch` que instala C-16.
- **Exclusiones**: auditoría y exportación 1-clic (C-14), importación Excel (sin backend), facturación electrónica AFIP/ARCA y presentación electrónica de OS (v2), multi-sucursal real (solo el campo `sucursal` del sillón), pantallas de C-16, PWA pública de C-15, cambios de backend/migraciones/seeds, CORS.
