# Proposal

## Why

La tabla `auditoria` viene registrando cada cambio crítico desde C-02 (`RN-SE-01`) y ya es append-only a nivel de permisos de base de datos, pero **nadie puede consultarla ni exportarla**: el Dueño no tiene forma de responder un pedido de acceso (Ley 25.326) ni de revisar quién cambió qué, y tampoco existe una página legal pública ni un mecanismo de portabilidad de datos del paciente (`RN-SE-02`). C-14 cierra la Fase 5 transversal y el Flujo 7 del roadmap, agregando **lectura y exportación** sobre lo que ya se escribe. No hace falta un middleware nuevo: el trail ya se registra en agenda, clínica, pacientes, presupuestos, caja, Mercado Pago, lista de espera y liquidaciones.

## What Changes

- **Consulta del trail**: nuevo `GET /api/auditoria` con filtros por entidad, identificador de entidad, actor, acción y período, paginación por keyset (sin `OFFSET` profundo) y orden descendente. Solo Dueño. `tenant_id` sale siempre del token (`R4`).
- **Inmutabilidad visible por API**: no se agregan rutas de escritura sobre auditoría; un intento de borrar o editar se rechaza por RBAC (`403`/`405`) y, a nivel DB, por los permisos `INSERT+SELECT` ya vigentes (`SQLSTATE 42501`), con tests explícitos en ambos niveles (`R7`, `RN-SE-01`).
- **Exportación en 1 clic**: `GET /api/exportacion/{dataset}` para `agenda`, `pacientes`, `caja` y `liquidaciones`, en CSV o JSON, generada siempre en el servidor. Solo Dueño: Recepción y Odontólogo reciben `403` (desvío consciente de la matriz de `knowledge-base/03_actores_y_roles.md:32,34`, justificado en el design). Bajo un umbral configurable de filas responde el archivo de forma directa; por encima encola un job en el worker Redis existente y expone estado + descarga con vencimiento fijo de 24 h.
- **PHI minimizada en archivos**: los datasets `caja` y `liquidaciones` enmascaran DNI, CUIT/CUIL y teléfonos en sus textos libres; el nombre de archivo se arma solo con dataset, período e identificador opaco. Rango de fechas validado (`desde <= hasta`, `hasta <= ahora`, máximo 366 días) con `400` accionable.
- **Exportación de datos del paciente** (`RN-SE-02`): `GET /api/pacientes/{id}/exportar-datos` con un paquete JSON de alcance mínimo (contacto, turnos, ficha clínica, evoluciones, odontograma, presupuestos, consentimientos y movimientos propios), solo Dueño, sin exponer datos de terceros ni permitir enumeración.
- **Página legal pública**: ruta pública `/privacidad` en la PWA con Ley 25.326 (datos personales) y Ley 26.529 (HCE), derechos, retención y vía de contacto, sin PHI ni datos de pacientes.
- **Pantalla interna del Dueño**: sección de auditoría con filtros, detalle antes/después y panel de exportación en 1 clic, oculta para Recepción y Odontólogo. Botón de exportación del paciente en su ficha.
- **Sin migración de base de datos**: se leen tablas existentes. El único cambio de infraestructura es un volumen compartido entre `api` y `worker` para los archivos exportados asíncronos.
- **Sin cambios de contrato** en endpoints ya entregados, salvo la ruta nueva `exportar-datos` colgada de `/api/pacientes/{id}` y el permiso `exportar` del recurso `pacientes` para Dueño.

## Capabilities

### New Capabilities

- `auditoria-exportacion`: consulta del trail append-only con filtros y paginación, inmutabilidad expuesta, exportación tenant-wide en 1 clic (directa y asíncrona), registro auditable de cada exportación, página legal pública y pantalla del Dueño para auditar y exportar.

### Modified Capabilities

- `pacientes`: se agrega la exportación del paquete de datos del paciente (`RN-SE-02`) restringida al Dueño, con alcance mínimo, protección contra IDOR y registro en auditoría.

## Impact

- **Backend**: routers nuevos `app/api/routers/auditoria.py` y `app/api/routers/exportacion.py`; schemas `schemas_auditoria.py` y `schemas_exportacion.py`; capa de aplicación `app/application/auditoria.py` (lectura) y `app/application/exportacion.py` (datasets + jobs + purga + paquete del paciente); `app/shared/sanitizar_phi.py` (enmascarado de identificadores en texto libre, con tests propios); `app/api/routers/pacientes.py` (ruta de exportación); `app/domain/rbac.py` (nuevo recurso `EXPORTACION_TENANT` y `EXPORTAR` en `PACIENTES`); `app/workers/main.py` (tipo de job `exportar_dataset` y barrido de vencidos); `app/shared/settings.py` (umbral y directorio de exportaciones, sin TTL configurable); `app/main.py` (registro de routers).
- **Frontend**: `features/auditoria/` (página y cliente API), `features/legal/PaginaLegalPage.tsx`, `features/pacientes/PacientesPage.tsx`, `shared/rbac.ts`, `shared/LayoutInterno.tsx`, `main.tsx` (rutas internas y pública), enlaces desde `HomePage` y el layout interno.
- **Infra**: `docker-compose.yml` (volumen compartido `exportaciones` entre `api` y `worker`) y `.env.example` con las variables nuevas. Sin migración Alembic.
- **Tests**: consulta y filtros del trail, matriz de 3 roles sobre trail + cuatro datasets + paquete, aislamiento entre dos tenants, keyset (incluidos `created_at` empatados y cursor corrupto), inmutabilidad API + DB, exports CSV/JSON por dataset con columnas exactas, enmascarado de identificadores en caja y liquidaciones, validación del rango de fechas, umbral sync/async en el borde (5000/5001), fallas del worker y de Redis, purga de archivos vencidos, descarga de job, expiración/tenant ajeno, paquete del paciente (incluido paciente sin actividad y adjuntos sin nombre) y ausencia de PHI en logs/URLs/nombres de archivo/eventos. Todos contra DB real (Postgres en contenedor) y fixtures sintéticos (`R11`, `R13`).

### Riesgos y consultas al PO

- **RBAC más restrictivo que la KB**: C-14 entrega el trail, los cuatro datasets y el paquete solo al Dueño, mientras `03_actores_y_roles.md:32,34` da exportación parcial a Recepción (agenda/caja + liquidaciones OS) y a Odontólogo (clínica propia). El argumento es mínimo necesario (`RN-SE-02`) y evitar copias de PHI en archivos que se comparten con terceros. **Consulta al PO**: ¿se habilita la exportación parcial en un change posterior? Si sí, implica scoping por actor y reescribir la matriz y sus tests; `knowledge-base/` no se edita desde C-14.
- **Padrón completo de pacientes sin período**: el dataset `pacientes` exporta todos los pacientes del consultorio; es un volcado masivo de PHI a un archivo. **Consulta al PO**: confirmar que es lo esperado o exigir un rango.
- **Enmascarado por patrones**: detecta DNI, CUIT/CUIL y teléfonos, no nombres sueltos en un texto libre (“Seña de Juan”). Se acepta como riesgo residual hasta estructurar caja en otro change.
- **TTL fijo de 24 h** para los jobs: no se configura por consultorio. Si el PO necesita otro plazo, se agrega después con un caso de uso medido.
