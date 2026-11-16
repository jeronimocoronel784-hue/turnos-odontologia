# Design

## Context

Ver `proposal.md` — Why. El estado actual que condiciona el cómo:

- **Backend**: caja (`/api/senas`, `/api/caja/movimientos`, `/api/caja/cierre`, `/api/caja/turnos/{id}/liquidacion|cobrar`), obras sociales (`/api/os/cobertura`, `/api/liquidaciones` con `cerrar`/`resultado`/`exportar`), catálogo (`/api/prestaciones`, `/api/sillones`, `/api/coberturas`, `/api/tenant/politicas`) y usuarios (`/api/usuarios`, `PATCH /{id}/rol`) ya existen, con RBAC propio en `src/backend/app/domain/rbac.py` (acciones `REABRIR_CIERRE` y `EXPORTAR` incluidas). Los montos se calculan en el servidor: `diferencia = total_contado − total_sistema` en `cerrar_caja`, y el saldo de la atención en `calcular_liquidacion_turno`.
- **Frontend**: C-15 dejó la PWA pública; C-16 dejó **propuesto** (0/37 tareas) el shell interno con `shared/sesion.ts`, `apiFetch`, `shared/rbac.ts`, layout y guards. C-17 **no reimplementa** ese shell: lo consume. Sin C-16 aplicado, el primer paso de C-17 es bloqueante.
- **Restricciones del proyecto**: R5 (sin `any`, TS estricto), R6/R9 (sin credenciales ni datos personales en storage, sin PHI en logs), R8 (montos solo del servidor), R11 (≥2 casos por comportamiento), governance MEDIO.
- **Restricciones del entorno**: `caja.py` **no commitea** (0 `session.commit()` en 700+ líneas). Todo el flujo de caja responde `2xx` y no persiste. Auditado como riesgo alto en `proposal.md`.
- **Ausencia de backend de auditoría/exportación**: no existe router de auditoría ni de exportación 1-clic; `GET /api/liquidaciones/{id}/exportar` es el único export existente. La UI de auditoría queda fuera de C-17.

## Goals / Non-Goals

**Goals**

- Pantallas que cubran el ciclo del dinero: registrar → cobrar → cerrar → liquidar → exportar.
- Que ningún importe mostrado o enviado se calcule en el cliente.
- Reutilizar el shell de C-16 sin duplicar sesión, cliente HTTP ni guards.
- Que el dueño pueda configurar el consultorio sin tocar Swagger.
- Un cierre de producto consistente: estados, mensajes y responsive homogéneos con C-16.

**Non-Goals**

- Auditoría consultable, exportación 1-clic de agenda/pacientes/caja, export del paciente y página legal (C-14, sin endpoints).
- Importación Excel (US-063): requiere endpoint backend inexistente.
- Presentación electrónica de OS y facturación AFIP/ARCA (v2, RN-OS-03).
- Multi-sucursal real: solo se expone el campo `sucursal` del sillón.
- Cambios de backend, migraciones, seeds, CORS.
- Rehacer el shell de C-16 o las pantallas de agenda/clínica/comunicaciones.

## Decisions

### D1 — C-17 consume el shell de C-16, no lo redefine

`shared/sesion.ts`, `apiFetch`, `shared/rbac.ts` y el layout protegido se importan tal como los deja C-16. C-17 solo **extiende**: `rbac.ts` suma `CAJA`, `LIQUIDACIONES`, `CONFIGURACION`, `USUARIOS` y las acciones `REABRIR_CIERRE` / `EXPORTAR`; el menú suma las secciones nuevas.

- *Por qué*: duplicar sesión o cliente HTTP multiplicaría los refrescos de token y rompería la regla de "un solo refresh" que C-16 garantiza con su test.
- *Alternativa descartada*: crear un `api-client-caja.ts` aparte (dos clientes que divergen en el manejo de `401`).
- *Consecuencia operativa*: el apply de C-17 arranca por una verificación de que el shell existe; si C-16 no está aplicado, se frena y se avisa en vez de reimplementarlo.

### D2 — RBAC extendido con paridad verificada

La matriz del cliente replica exactamente las filas de `rbac.py` para los recursos nuevos, incluidas las dos acciones no-CRUD:

| Recurso | Dueño | Recepción | Odontólogo |
|---|---|---|---|
| `CAJA` | CRUD + reabrir cierre | CRUD (sin reabrir) | leer |
| `LIQUIDACIONES` | CRUD + exportar | CRUD + exportar | leer |
| `CONFIGURACION` | CRUD | leer | leer |
| `USUARIOS` | CRUD | leer | leer |

Un test de paridad fija estas filas y falla si alguien toca `rbac.py` sin actualizar el espejo. Aun así, la UI nunca asume permiso: el `403` real se muestra.

- *Alternativa descartada*: endpoint que exponga la matriz (cambio backend); checks `if (rol === "dueno")` dispersos (drift garantizado).

### D3 — Dinero: el cliente nunca suma

Toda cifra que se muestra u se envía proviene de un campo del servidor: `MovimientoCajaRead.monto`, `CierreCajaRead.total_sistema|total_contado|diferencia`, `LiquidacionTurnoRead.{precio_particular, cobertura_os, sena_cobrada, saldo}`, `LiquidacionOSRead.{total, total_reconocido}`, `CoberturaLookupRead.{precio_particular, cobertura, monto_a_cargo}`.

- Los importes se manejan como **string decimal** de la respuesta y se formatean con `Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS" })`, sin `parseFloat` para decidir nada.
- La única aritmética permitida en el cliente es de presentación: signo de la diferencia (`>`/`<`/`=` contra `"0.00"` como string normalizado) para elegir la etiqueta "sobrante"/"faltante"/"cuadrada".
- El panel del día usa los totales del servidor y **conteos**, nunca sumas de dinero propias.

- *Por qué*: R8 es una regla dura del proyecto y un redondeo en el cliente genera diferencias de caja que después nadie explica.
- *Alternativa descartada*: `number` para montos (pierde centavos y habilita sumas accidentales).

### D4 — Cierre de caja: confirmación explícita del descuadre

Al cerrar, el formulario pide `total_contado`; si al calcular la diferencia (`contado − sistema`) el resultado no es `"0.00"`, se abre un diálogo de confirmación que dice si es sobrante o faltante y el monto, y solo entonces se envía. El cierre cerrado se pinta sin acciones; la reapertura existe únicamente si `permite(roles, CAJA, REABRIR_CIERRE)` y exige motivo.

- *Por qué*: RN-PA-05 exige que la discrepancia no se cierre sola; el backend la acepta pero la audita, así que la fricción tiene que estar en la UI.
- *Alternativa descartada*: bloquear el cierre con diferencia (el backend lo permite y hay casos legítimos, ej. propina o redondeo).

### D5 — Descarga de exportaciones con `fetch` + blob

`GET /api/liquidaciones/{id}/exportar?formato=csv|json` se pide con `apiFetch` en modo blob (`credentials: "include"` + Bearer), se toma el nombre de archivo del `Content-Disposition` (fallback `liquidacion-{os}-{periodo}.{ext}`) y se dispara la descarga con `URL.createObjectURL` revocado después.

- *Por qué*: un `<a href>` directo no lleva el header `Authorization` del access token en memoria.
- *Alternativa descartada*: abrir la URL en pestaña nueva (401 por falta de token); armar el CSV en el cliente (viola R8 y duplica el formato del servidor).

### D6 — Máquina de estados de la liquidación reflejada, no inventada

La UI deriva las acciones de `LiquidacionOSRead.estado` (`borrador → presentada → pagada | con_debitos`; `anulada` terminal) y de los flags del servidor: `turnos_sin_cobertura`, `advertencias`, `arancel_vencido` en los detalles. Si el backend rechaza una transición, se muestra el mensaje y se recarga el estado real en lugar de revertir a ciegas.

- *Por qué*: RN-OS-02/03 definen el ciclo y el servidor ya lo valida; replicar reglas en el cliente crearía dos verdades.
- *Alternativa descartada*: espejar la máquina de estados completa en TypeScript (mantenimiento duplicado).

### D7 — Administración: desactivar en vez de borrar

Prestaciones, sillones y coberturas se desactivan (`DELETE` del backend = baja lógica). Ninguna pantalla ofrece borrado físico. El cambio de precio/arancel se advierte como "no afecta liquidaciones ni cobros ya generados".

- *Por qué*: R7 (nunca hard delete) y RN-OS-02 (integridad histórica de lo liquidado).
- *Alternativa descartada*: `DELETE` real (rompe turnos y liquidaciones históricas).

### D8 — Usuarios: alta y cambio de rol, cero credenciales en pantalla

El alta pide email, nombre, rol, matrícula (si odontólogo) y contraseña; la contraseña se envía y se descarta del estado del formulario al recibir `201`, sin volver a mostrarse. El listado solo pinta campos de `UsuarioRead` (sin hash). El cambio de rol avisa que impacta en los accesos del usuario.

- *Por qué*: R9 y la matriz §03 (Dueño CRUD, resto lectura).
- *Alternativa descartada*: mostrar "contraseña temporal" tras el alta (dato sensible en pantalla y en posibles capturas).

### D9 — Panel del día compuesto por consultas existentes

El panel combina cuatro consultas en paralelo con `staleTime` corto: cierres de la fecha (`/api/caja/cierre`), liquidaciones (`/api/liquidaciones`), señas (`/api/senas`) y agenda del día (`/api/agenda`). Cada tarjeta muestra conteos y los importes que vienen en cada registro; no hay endpoint de dashboard y no se agrega uno.

- *Por qué*: entrega valor operativo sin tocar backend.
- *Límite asumido*: con muchos registros, el panel trae listas completas del día; aceptable para el piloto y anotado como deuda.

### D10 — Consistencia visual y accesibilidad medible

Se reutilizan los componentes de estado de C-16 (`ErrorApi` → mensaje con qué pasó/por qué/cómo seguir, `EstadoVacio`, `Cargando`) y se suman dos piezas compartidas: tabla con encabezados accesibles y `CampoFormulario` con label asociado y error anunciado. Tokens de diseño ya existentes (Tailwind) sin sumar librería de UI. Criterios verificables: 360 px sin scroll horizontal, foco visible en todo control, estado nunca solo por color, etiqueta en cada campo.

- *Por qué*: el "polish final" sin criterios medibles se vuelve inverificable; con estos cuatro se puede testear y revisar.
- *Alternativa descartada*: adoptar un design system externo (dependencia y rediseño fuera de alcance).

### D11 — Tests heredados de C-16, extendidos por feature

Se usa el `render.tsx` con `QueryClientProvider` + `MemoryRouter` y el doble de `fetch` de C-16. Casos por feature: caja (movimiento, cierre con diferencia, 409 de fecha duplicada), cobro (saldo, cobro `201`, saldo cero), señas (cobro, ausencia), OS (cobertura vigente/sin cobertura, liquidación `409`, débito sin motivo, export `403`), admin (alta con validación, desactivar, matrícula obligatoria, cambio de rol), panel (sin cierre abierto, sin liquidaciones) y storage (nada en `localStorage`).

- *Por qué*: R11 y continuidad con el runner que instala C-16.
- *Alternativa descartada*: MSW (peso innecesario para dobles de un solo endpoint por test).

### D12 — Rutas y estructura

```text
src/frontend/src/features/
  caja/        CajaPage, MovimientoForm, CierrePanel, ReabrirDialog, api.ts, queries.ts
  cobros/      CobroTurnoPage, SenaList, SenaAcciones, api.ts, queries.ts
  os/          CoberturaLookup, LiquidacionesPage, LiquidacionDetalle, DebitoForm, ExportarAcciones, api.ts, queries.ts
  admin/       PrestacionesPage, SillonesPage, CoberturasPage, PoliticasPage, UsuariosPage, api.ts, queries.ts
  panel/       PanelPage, api.ts, queries.ts
```

Rutas bajo `/app`: `/app/caja`, `/app/caja/cierres/:id`, `/app/cobros/turno/:turnoId`, `/app/os/liquidaciones`, `/app/os/liquidaciones/:id`, `/app/admin/{prestaciones,sillones,coberturas,politicas,usuarios}`, `/app/panel`. Sin tocar `/app/{agenda,pacientes,...}` de C-16 ni las rutas públicas.

## Risks / Trade-offs

- **[`caja.py` no persiste]** → Movimientos, cierres, reaperturas, cobros y señas responden OK y no guardan. Mitigación: riesgo explícito en `proposal.md`, mensaje en la UI cuando el alta "no aparece al refrescar", y **C-19 (fix de commits) como requisito previo al apply**. No se parchea el backend desde C-17.
- **[C-16 sin aplicar]** → El shell no existe (0/37). Mitigación: tarea 0 de verificación de prerrequisitos; el apply se detiene con mensaje claro en lugar de reimplementar sesión.
- **[C-14 pendiente]** → Auditoría y exportación 1-clic no se entregan; se documenta en `CHANGES.md` al cerrar para que nadie las busque en la UI.
- **[Montos como string]** → Comparaciones y ordenamientos de importes requieren normalización; mitigación: un único `formattersMonto` + comparador decimal compartido, con tests de borde (`0.00`, negativos, miles).
- **[Descarga con blob en jsdom]** → `URL.createObjectURL` no existe en el entorno de test; mitigación: stub en `test/setup.ts` y verificación manual del archivo descargado.
- **[Panel con listas completas del día]** → Costo lineal con el volumen; aceptable en piloto, deuda anotada.
- **[Polish subjetivo]** → Se acota a cuatro criterios medibles (360 px, foco, etiquetas, estado no solo color) revisables con tests de render y lista de cotejo.
- **[Cierre con diferencia]** → La confirmación puede volverse ruido si se dispara por redondeos; mitigación: comparación sobre el string normalizado a dos decimales que devuelve el servidor.

## Migration Plan

- **Sin migraciones ni cambios de API**: aditivo en frontend.
- **Orden de despliegue**: (1) verificar shell de C-16; (2) tipos/formatters/RBAC extendido; (3) caja → cobros y señas → OS → admin → panel; (4) polish y accesibilidad; (5) CI. Cada paso deja `tsc --noEmit` y `test:run` en verde.
- **Rollback**: revertir el commit del change; las rutas nuevas son aditivas y no colisionan con C-16 ni con la PWA pública.
- **Dependencia externa**: C-19 (commits de caja) debe aterrizar antes de la demo de caja; sin él la UI funciona y no persiste.

## Open Questions

- **Origen de los textos legales y del nombre comercial** de la OS en la exportación: hoy se usa el string del padrón; si el PO quiere normalizar nombres, se ajusta la configuración, no el diseño.
- **¿El panel del dueño debe incluir comparación contra el día anterior?** No hay endpoint agregado; queda para cuando exista un dashboard backend.
- **¿La exportación de agenda/pacientes/caja se suma a C-14 o a un change propio?** Decisión de roadmap; C-17 no la incluye.
