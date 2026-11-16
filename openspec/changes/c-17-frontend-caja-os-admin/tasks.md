# Tasks

> TDD estricto por tarea: **RED** → **GREEN** → **TRIANGULATE** (≥2 casos por comportamiento, R11) → **REFACTOR**. Cada tarea se considera hecha solo con su verificación en verde y `tsc --noEmit` limpio. Gobernanza MEDIO: sin cambios en backend, migraciones ni seeds. Prerrequisito: C-16 aplicado (shell) y, para la demo de caja, C-19 (commits).

## 1. Prerrequisitos y base compartida

- [ ] 1.1 Verificar que el shell de C-16 existe (`shared/sesion.ts`, `apiFetch`, `shared/rbac.ts`, layout protegido y runner de vitest); si falta, detener el apply y reportarlo como bloqueante; verificar con `npm run test:run` en verde y un smoke que monte `/app` con sesión simulada.
- [ ] 1.2 Sumar a `src/frontend/src/shared/api-types.ts` los tipos de caja, OS, catálogo admin y usuarios (`SenaRead`, `MovimientoCajaRead`, `CierreCajaRead`, `LiquidacionTurnoRead`, `CobrarTurnoInput`, `CoberturaLookupRead`, `LiquidacionOSRead`, `LiquidacionOSDetalleRead`, `PrestacionRead`, `SillonRead`, `CoberturaOSRead`, `PoliticasRead`, `UsuarioRead`) sin `any`; verificar con `npm run build`.
- [ ] 1.3 Implementar `shared/formattersMonto.ts` (formato es-AR de moneda desde string decimal, comparación decimal a 2 posiciones y clasificación sobrante/faltante/cuadrada) con tests de 2 casos por función (`0.00`, negativo, miles, tres decimales del servidor).
- [ ] 1.4 Extender `shared/rbac.ts` con `CAJA`, `LIQUIDACIONES`, `CONFIGURACION`, `USUARIOS` y las acciones `REABRIR_CIERRE`/`EXPORTAR`; tests de paridad con las filas de `src/backend/app/domain/rbac.py` y denegación por defecto con rol desconocido.
- [ ] 1.5 Crear los componentes compartidos de tabla, campo de formulario (label asociado + error anunciado) y confirmación de acción destructiva; tests: tabla con encabezados accesibles, campo inválido anuncia el error y confirmación exige aceptar antes de ejecutar.
- [ ] 1.6 Cablear en `main.tsx` las rutas nuevas bajo `/app` (`caja`, `caja/cierres/:id`, `cobros/turno/:turnoId`, `os/liquidaciones`, `os/liquidaciones/:id`, `admin/*`, `panel`) sin tocar las de C-16 ni las públicas; verificar con un test de rutas que una ruta de C-16 y una pública siguen resolviendo.

## 2. Caja: movimientos y cierre

- [ ] 2.1 Crear `features/caja/api.ts` y `queries.ts` (movimientos por rango/medio/tipo, cierres, cierre por id) con claves en `shared/query-keys.ts`; tests: arma la URL con los filtros elegidos y no consulta sin rango de fecha.
- [ ] 2.2 Implementar el listado de movimientos con filtros y columnas (tipo, concepto, medio, monto, cierre, creado por); tests: filtro por medio devuelve solo esos movimientos, listado vacío muestra estado vacío y el monto se muestra formateado desde el string del servidor.
- [ ] 2.3 Implementar alta de ingreso y egreso con validación local (concepto obligatorio, monto mayor a cero); tests: alta `201` agrega el movimiento con el monto del servidor, egreso se envía con `tipo: "egreso"`, faltantes o monto cero no llaman a la API.
- [ ] 2.4 Avisar cuando no hay cierre abierto al registrar un movimiento; tests: sin cierre abierto se muestra el aviso y el alta sigue permitida, con cierre abierto el aviso no aparece.
- [ ] 2.5 Implementar apertura de cierre por fecha y su manejo de duplicado; tests: `201` muestra el cierre abierto con fecha y autor, `409` abre el cierre existente y no crea uno nuevo, fecha vacía no llama a la API.
- [ ] 2.6 Implementar el cierre con `total_contado`, la visualización de `total_sistema`/`contado`/`diferencia` y la confirmación obligatoria cuando la diferencia no es cero; tests: cierre exacto no pide confirmación, cierre con faltante pide confirmación con el monto y la etiqueta correcta, confirmar envía y muestra los valores del servidor, contado negativo no se envía.
- [ ] 2.7 Implementar la vista de cierre cerrado como inmutable y la reapertura solo para Dueño con motivo; tests: cerrado no muestra acciones de cierre, recepción no ve "Reabrir" y un `403` forzado se muestra, dueño reabre con motivo y el motivo queda visible, reabrir sin motivo no envía.

## 3. Cobro de la atención y señas

- [ ] 3.1 Implementar la vista de cobro del turno con `GET /api/caja/turnos/{id}/liquidacion` (precio, cobertura, seña cobrada, saldo) sin cálculo local; tests: renderiza los cuatro importes del servidor y no los recalcula cuando cambia la cobertura; saldo cero deshabilita el cobro.
- [ ] 3.2 Implementar el cobro con medio de pago y su reflejo posterior; tests: `201` muestra el movimiento y la atención saldada, `409`/`422` muestran el mensaje del backend y conservan los montos de la última lectura.
- [ ] 3.3 Implementar el listado de señas por estado y sus acciones (cobrar, resolver cancelación con `ausente`, vencer); tests: filtro por estado, cobro deja la seña `cobrada`, ausencia retiene la seña según la respuesta del servidor y una acción no válida para el estado no se ofrece.
- [ ] 3.4 Manejar el `403` de caja para el odontólogo (solo lectura) y ocultar acciones de escritura; tests: odontólogo no ve alta de movimiento ni cierre, recepción sí, y el `403` forzado se muestra sin reintento.

## 4. Obras sociales: cobertura y liquidaciones

- [ ] 4.1 Implementar la consulta de cobertura (`GET /api/os/cobertura`) con precio, cobertura, a cargo y advertencia de arancel vencido; tests: cobertura vigente muestra los tres importes, sin cobertura muestra a cargo igual al particular, `arancel_vencido` muestra la advertencia del servidor.
- [ ] 4.2 Implementar el listado y alta de liquidaciones por OS/período con validación de formato y manejo de `409`; tests: `201` muestra borrador con total del servidor, `409` ofrece abrir la existente, período inválido no llama a la API.
- [ ] 4.3 Implementar el detalle de liquidación con estado, totales, detalles por turno, `turnos_sin_cobertura` y `advertencias`; tests: borrador lista sus turnos con montos del servidor, advertencias se muestran destacadas y estado vacío explica que solo entran turnos finalizados.
- [ ] 4.4 Implementar cierre, resultado (`pagada`/`con_debitos`) y débitos con motivo obligatorio; tests: cierre deja la liquidación en `presentada`, débito sin motivo no se envía, resultado `con_debitos` muestra total reconocido y detalle.
- [ ] 4.5 Implementar anulación con motivo y el bloqueo de acciones sobre liquidaciones anuladas; tests: anular sin motivo no envía, anular con motivo muestra estado `anulada` y su motivo, anulada no ofrece cierre/resultado/exportación.
- [ ] 4.6 Implementar la descarga CSV/JSON desde `GET /api/liquidaciones/{id}/exportar` con blob, `Content-Disposition` y limpieza de la URL temporal; tests: CSV descarga con el nombre del header, JSON descarga distinto del CSV, `403`/`5xx` no genera archivo vacío, odontólogo no ve la acción de exportar.

## 5. Administración del consultorio

- [ ] 5.1 Implementar `features/admin/api.ts` y `queries.ts` para prestaciones, sillones, coberturas, políticas y usuarios; tests: cada query pega en la ruta correcta y las mutaciones invalidan su clave.
- [ ] 5.2 Implementar el ABM de prestaciones (duración, precio, seña con monto, invasiva, activa) con desactivación lógica; tests: alta `201` aparece con el precio del servidor, seña sin monto no se envía, precio negativo o duración inválida no llaman a la API, desactivar deja la prestación visible como inactiva.
- [ ] 5.3 Implementar el ABM de sillones con sucursal y desactivación; tests: alta `201` con sucursal `central` por defecto, nombre vacío no se envía, desactivar lo marca inactivo con el aviso de que no se puede agendar.
- [ ] 5.4 Implementar el padrón de coberturas (OS × prestación × arancel × copago × vigencia) con desactivación y aviso de impacto histórico; tests: alta `201`, vigencia invertida no se envía, edición de arancel muestra el aviso de que no altera liquidaciones ya generadas.
- [ ] 5.5 Implementar la edición de políticas del consultorio con rangos validados; tests: guardar `200` muestra los valores del servidor, porcentaje fuera de rango no se envía, guardar sin cambios no dispara `PATCH`.
- [ ] 5.6 Implementar usuarios: listado sin credenciales, alta con matrícula obligatoria para odontólogo y cambio de rol; tests: alta `201` no vuelve a mostrar la contraseña, odontólogo sin matrícula no se envía, `409` de email duplicado no agrega el usuario, cambio de rol muestra el rol nuevo.
- [ ] 5.7 Ocultar las acciones de escritura de administración a recepción y odontólogo y manejar el `403` real; tests: recepción ve solo lectura en prestaciones/sillones/coberturas/políticas, odontólogo no ve alta ni cambio de rol en usuarios, escritura forzada muestra el mensaje de permiso denegado.

## 6. Panel del consultorio

- [ ] 6.1 Implementar `features/panel` con las cuatro consultas del día (cierres, liquidaciones, señas, agenda) y sus claves de caché; tests: carga las cuatro en paralelo y muestra conteos correctos con datos de doble.
- [ ] 6.2 Implementar las tarjetas del panel con montos del servidor y el caso "caja sin abrir"; tests: cierre abierto muestra sistema/contado/diferencia, sin cierre ofrece abrir la caja y no muestra totales en cero como cuadrados, sin liquidaciones muestra estado vacío.
- [ ] 6.3 Implementar el refresco acotado del panel (visible, se detiene en segundo plano) y el fallo parcial; tests con fake timers: refresca al vencer el intervalo, no refresca con la pestaña oculta y un fallo de red conserva las tarjetas ya cargadas.

## 7. Polish, accesibilidad y consistencia

- [ ] 7.1 Unificar estados de carga/vacío/error de las pantallas nuevas con los componentes compartidos; tests: las cuatro features muestran el mismo patrón de carga y un error accionable con qué pasó/por qué/cómo seguir.
- [ ] 7.2 Verificar responsive a 360 px en caja, liquidaciones, admin y panel; tests: los cuatro renderizan sin contenedor con scroll horizontal y las acciones principales quedan visibles.
- [ ] 7.3 Verificar navegación por teclado y etiquetas en los formularios nuevos; tests: el foco es visible en el primer control, el orden de tab sigue el visual y todo campo obligatorio tiene label y error asociado.
- [ ] 7.4 Verificar que ningún estado se transmita solo por color en cierres, liquidaciones y señas; tests: cada estado tiene su etiqueta textual además del color.
- [ ] 7.5 Verificar que no se escribe nada en `localStorage`/`sessionStorage` en caja, OS y admin (incluido el alta de usuario); tests: espías sobre el storage en los flujos principales y en el cierre de sesión.

## 8. Verificación de integración y cierre

- [ ] 8.1 Correr `npm run build` y `npm run test:run` en `src/frontend` y dejar la salida registrada; verificar ambos en verde.
- [ ] 8.2 Verificación manual contra la API real con los usuarios demo: abrir cierre, registrar movimiento, cerrar caja y cobrar un turno; documentar como bloqueado lo que no persista por el bug de `caja.py` con referencia a C-19.
- [ ] 8.3 Verificación manual de obras sociales: consultar cobertura, crear liquidación, registrar débito con motivo y descargar CSV; verificar que el archivo descargado coincide con la respuesta del servidor.
- [ ] 8.4 Actualizar `CHANGES.md` (estado de C-17, dependencias reales: C-16 aplicado por el shell y C-19 por la persistencia de caja) y dejar constancia de que auditoría/exportación 1-clic quedan en C-14.
- [ ] 8.5 Sumar los tests nuevos al job `frontend` de `.github/workflows/ci.yml` si C-16 no lo hizo, y verificar que el YAML sigue válido y corre `npm ci && npm run test:run`.
