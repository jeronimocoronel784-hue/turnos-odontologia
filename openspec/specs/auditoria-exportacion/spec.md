# auditoria-exportacion Specification

## Purpose

Permitir que el Dueño consulte el trail append-only del consultorio y exporte sus datos (agenda, pacientes, caja y liquidaciones) en CSV o JSON, además de publicar la información legal de privacidad y HCE que exige la Ley 25.326 (`RN-SE-01`, `RN-SE-02`, Flujo 7).

## Requirements

### Requirement: Consulta del trail de auditoría con filtros y paginación

El sistema MUST exponer `GET /api/auditoria` para leer la tabla append-only con filtros opcionales por `entidad`, `entidad_id`, `actor_id`, `accion`, `desde` y `hasta`. MUST ordenar por `created_at` descendente y paginar por keyset (cursor opaco), sin `OFFSET` profundo. El `tenant_id` MUST salir del token y NUNCA aceptarse como filtro (`R4`). El límite MUST ser configurable entre 1 y 200, con default 50, y la respuesta MUST usar schemas Pydantic explícitos, sin exponer el modelo ORM (`R1`).

#### Scenario: Filtros combinados devuelven solo los eventos que coinciden

- **GIVEN** eventos de auditoría del tenant A de las entidades `turno` y `paciente`, de dos actores distintos y en fechas distintas
- **WHEN** el Dueño consulta `/api/auditoria?entidad=turno&actor_id=<actor>&desde=<fecha>&hasta=<fecha>`
- **THEN** el sistema devuelve solo los eventos de la entidad `turno`, de ese actor y dentro del rango, ordenados del más reciente al más antiguo

#### Scenario: Paginación keyset sin duplicados ni huecos

- **GIVEN** cinco eventos de auditoría del tenant A con la misma entidad
- **WHEN** el Dueño pide `limite=2`, luego usa el `siguiente_cursor` recibido y repite hasta agotar la página
- **THEN** los cinco eventos aparecen exactamente una vez y la última página devuelve `siguiente_cursor = null`

#### Scenario: Paginación keyset con created_at empatados

- **GIVEN** tres eventos del tenant A con el mismo `created_at` y distinto `id`
- **WHEN** el Dueño pide `limite=2` y luego sigue con el `siguiente_cursor`
- **THEN** los tres eventos aparecen exactamente una vez, sin duplicados ni huecos, y entre los empatados el orden es por `id` descendente

#### Scenario: Cursor corrupto se rechaza

- **WHEN** el Dueño consulta el trail con un `cursor` que no es base64url de `{"created_at","id"}`
- **THEN** el sistema responde `422` con un mensaje rioplatense que pide repetir la consulta sin cursor, sin ignorarlo en silencio

#### Scenario: Fechas sin offset se interpretan en ART

- **GIVEN** eventos con `created_at` en UTC cerca del cambio de día
- **WHEN** el Dueño consulta con `desde=2026-11-01T00:00:00` sin offset
- **THEN** el sistema lo interpreta como `2026-11-01T00:00:00-03:00` (`America/Argentina/Buenos_Aires`) y devuelve los eventos de ese rango

#### Scenario: Rango de fechas inválido se rechaza

- **WHEN** el Dueño consulta el trail con `desde` posterior a `hasta`
- **THEN** el sistema responde `422` con un mensaje rioplatense que explica que el rango de fechas está al revés y cómo corregirlo (`RN-GL-02`)

#### Scenario: Límite fuera de rango se rechaza

- **WHEN** el Dueño consulta el trail con `limite=0` o `limite=500`
- **THEN** el sistema responde `422` con el rango permitido (1 a 200) en el mensaje

### Requirement: Acceso al trail y a las exportaciones restringido al Dueño

Solo el rol Dueño MUST poder consultar el trail, exportar los cuatro datasets y pedir el paquete de datos del paciente. Recepción y Odontólogo MUST recibir `403` en los tres caminos, con mensaje rioplatense accionable y sin revelar los datos ni su existencia (`RN-GL-02`, `RN-SE-02`). No existe export parcial: el desvío de `knowledge-base/03_actores_y_roles.md:32,34` se documenta en el design.

#### Scenario: Dueño accede a los tres caminos

- **WHEN** un usuario con rol `dueno` consulta `/api/auditoria`, exporta cada uno de los cuatro datasets y pide el paquete de datos de un paciente de su consultorio
- **THEN** el sistema responde `200` en los seis pedidos, con los datos de su consultorio

#### Scenario: Recepción no accede al trail

- **WHEN** un usuario con rol `recepcion` consulta `/api/auditoria`
- **THEN** el sistema responde `403` y el mensaje le indica pedirle el permiso al Dueño

#### Scenario: Recepción no exporta ninguno de los cuatro datasets

- **WHEN** un usuario con rol `recepcion` pide `GET /api/exportacion/agenda`, `pacientes`, `caja` y `liquidaciones`, en CSV y en JSON
- **THEN** las ocho respuestas son `403` y ninguna incluye filas ni un archivo descargable

#### Scenario: Odontólogo no accede al trail

- **WHEN** un usuario con rol `odontologo` consulta `/api/auditoria`
- **THEN** el sistema responde `403` sin devolver eventos

#### Scenario: Odontólogo no exporta ninguno de los cuatro datasets

- **WHEN** un usuario con rol `odontologo` pide `GET /api/exportacion/agenda`, `pacientes`, `caja` y `liquidaciones`
- **THEN** las cuatro respuestas son `403` y no se genera ningún archivo, ni siquiera el de su propia agenda o clínica

#### Scenario: Recepción y Odontólogo no exportan el paquete del paciente

- **WHEN** un usuario con rol `recepcion` u `odontologo` pide `GET /api/pacientes/{id}/exportar-datos`
- **THEN** el sistema responde `403` en ambos casos y no devuelve ningún dato del paciente

### Requirement: Aislamiento multi-tenant del trail y de las exportaciones

Toda consulta del trail y toda exportación MUST filtrar por el `tenant_id` del token (`R4`). Un `tenant_id` enviado por query MUST ignorarse y NUNCA ampliar el alcance. Ninguna fila de otro consultorio MUST aparecer en la lectura, en el archivo exportado ni en el conteo de filas.

#### Scenario: El trail solo devuelve eventos del consultorio del token

- **GIVEN** eventos de auditoría del tenant A y del tenant B
- **WHEN** el Dueño del tenant A consulta el trail
- **THEN** el sistema devuelve solo eventos del tenant A y ninguno del tenant B

#### Scenario: La exportación solo contiene datos del consultorio del token

- **GIVEN** turnos, pacientes, movimientos de caja y liquidaciones de los tenants A y B en el mismo período
- **WHEN** el Dueño del tenant A exporta cada dataset
- **THEN** el archivo contiene solo filas del tenant A, aunque existan filas del tenant B con las mismas fechas

#### Scenario: Un tenant_id en query no amplía el alcance

- **WHEN** el Dueño del tenant A consulta `/api/auditoria?tenant_id=<tenant B>` o exporta con ese parámetro
- **THEN** el sistema sigue devolviendo solo datos del tenant A y no acepta el valor enviado por el cliente

### Requirement: Inmutabilidad de la auditoría expuesta por la API

El sistema MUST NOT exponer rutas de escritura sobre `/api/auditoria` ni sobre ningún evento del trail. Un intento de modificar o borrar MUST rechazarse: por HTTP sin ruta (`405`), por RBAC (ningún rol tiene `borrar` sobre auditoría) y por la base de datos con `SQLSTATE 42501` (`RN-SE-01`, `R7`).

#### Scenario: Borrado por API rechazado

- **WHEN** cualquier usuario autenticado intenta `DELETE`, `PUT` o `PATCH` sobre `/api/auditoria` o `/api/auditoria/{id}`
- **THEN** el sistema responde `405` y el evento sigue existiendo

#### Scenario: Ningún rol puede borrar auditoría en la matriz RBAC

- **WHEN** se evalúa la acción `borrar` sobre el recurso `auditoria` para Dueño, Recepción y Odontólogo
- **THEN** la matriz devuelve denegado para los tres roles

#### Scenario: La base de datos rechaza UPDATE y DELETE del rol app

- **GIVEN** un evento de auditoría persistido y una conexión con el rol app restringido en PostgreSQL
- **WHEN** se intenta `UPDATE` o `DELETE` sobre ese evento
- **THEN** PostgreSQL rechaza la operación con `SQLSTATE 42501` y el registro queda intacto

### Requirement: Exportación de datasets del consultorio en 1 clic

El sistema MUST exponer `GET /api/exportacion/{dataset}` con `dataset` en `agenda`, `pacientes`, `caja` o `liquidaciones` y `formato` en `csv` o `json`, generado siempre en el servidor. La respuesta MUST incluir `Content-Disposition` con nombre de archivo armado solo con dataset, período e identificador opaco, y `Cache-Control: no-store`.

#### Scenario: Sin rango se usa el mes en curso y el padrón completo

- **WHEN** el Dueño exporta `agenda`, `caja` y `liquidaciones` sin fechas, y luego `pacientes`
- **THEN** los tres primeros archivos cubren el mes calendario en curso en `America/Argentina/Buenos_Aires` y el de `pacientes` contiene el padrón completo

#### Scenario: Exportación CSV de agenda

- **WHEN** el Dueño solicita `GET /api/exportacion/agenda?formato=csv` sin rango de fechas
- **THEN** el sistema descarga un CSV con los turnos del mes en curso y las columnas exactas de `agenda`, sin DNI, sin contenido clínico y con `no-store`

#### Scenario: Exportación JSON de pacientes y caja

- **WHEN** el Dueño solicita los datasets `pacientes` y `caja` con `formato=json`
- **THEN** el sistema devuelve un JSON válido por dataset con las filas y montos calculados en el servidor (`R8`), sin reutilizar el CSV de una descarga previa

#### Scenario: El nombre del archivo no contiene datos del paciente

- **WHEN** el Dueño exporta cualquier dataset, en modo directo o asíncrono
- **THEN** el nombre del archivo contiene solo el dataset, el período y un identificador opaco: no aparece DNI, nombre, teléfono, obra social ni tenant

#### Scenario: Dataset desconocido se rechaza

- **WHEN** el Dueño solicita `GET /api/exportacion/clinica`
- **THEN** el sistema responde `422` con la lista de datasets permitidos y no genera ningún archivo

#### Scenario: Formato no soportado se rechaza

- **WHEN** el Dueño solicita un dataset con `formato=xlsx`
- **THEN** el sistema responde `422` con un mensaje rioplatense que indica usar `csv` o `json`

### Requirement: Columnas del dataset agenda y del dataset pacientes

El dataset `agenda` MUST exportar exactamente `turno_id`, `inicio`, `fin`, `estado`, `prestacion`, `profesional`, `matricula`, `sillon`, `paciente_id`, `paciente_nombre`, `sobreturno`. El dataset `pacientes` MUST exportar exactamente `paciente_id`, `nombre`, `dni`, `telefono`, `email`, `fecha_nac`, `obra_social`, `nro_afiliado`, `optin_wa`, `activo`, `created_at`. `agenda` MUST NOT incluir DNI, teléfono, email ni afiliado.

#### Scenario: Cabecera exacta de agenda

- **WHEN** el Dueño exporta `agenda` en CSV
- **THEN** la cabecera coincide exactamente con la lista del requisito, en el mismo orden, y no incluye `dni`, `telefono`, `email` ni `nro_afiliado`

#### Scenario: Cabecera exacta de pacientes

- **WHEN** el Dueño exporta `pacientes` en CSV
- **THEN** la cabecera coincide exactamente con la lista del requisito, en el mismo orden, e incluye activos e inactivos

### Requirement: Columnas del dataset caja y del dataset liquidaciones

El dataset `caja` MUST exportar exactamente `movimiento_id`, `created_at`, `tipo`, `concepto`, `medio`, `monto`, `turno_id`, `cierre_id`. El dataset `liquidaciones` MUST exportar exactamente `liquidacion_id`, `obra_social`, `periodo`, `estado`, `total`, `total_reconocido`, `turnos_sin_cobertura`, `observaciones`, `created_at`. `saldo_debito` MUST NOT exportarse porque es derivado (`total - total_reconocido`).

#### Scenario: Cabecera exacta de caja

- **WHEN** el Dueño exporta `caja` en CSV
- **THEN** la cabecera coincide exactamente con la lista del requisito y no aparece ningún dato identificatorio del paciente

#### Scenario: Cabecera exacta de liquidaciones sin el derivado

- **WHEN** el Dueño exporta `liquidaciones` en CSV
- **THEN** la cabecera coincide exactamente con la lista del requisito e incluye los dos totales, pero no `saldo_debito`

### Requirement: Validación del rango de fechas de la exportación

El sistema MUST validar que `desde <= hasta`, que `hasta <= ahora` y que el rango no supere **366 días**. Las fechas son ISO-8601 y, sin offset, se interpretan en `America/Argentina/Buenos_Aires`. Toda violación MUST responder `400` con mensaje rioplatense accionable (`RN-GL-02`), nunca `500`. El dataset `pacientes` MUST ignorar `desde`/`hasta` de forma documentada.

#### Scenario: Rango de fechas invertido se rechaza

- **WHEN** el Dueño pide `GET /api/exportacion/caja?desde=2026-11-10&hasta=2026-11-01`
- **THEN** el sistema responde `400` con un mensaje que explica que `desde` no puede ser posterior a `hasta` y no genera archivo ni job

#### Scenario: El rango no puede terminar en el futuro

- **WHEN** el Dueño pide `hasta` posterior a la hora actual
- **THEN** el sistema responde `400` con un mensaje que indica que `hasta` no puede ser futuro

#### Scenario: El rango máximo es de 366 días

- **WHEN** el Dueño pide un rango de 400 días
- **THEN** el sistema responde `400` con un mensaje que explica el máximo de 366 días y sugiere dividir el pedido en períodos más chicos

#### Scenario: Fecha mal formada se rechaza con 400

- **WHEN** el Dueño pide `desde=31/11/2026` o `hasta=ayer`
- **THEN** el sistema responde `400` con un mensaje rioplatense que pide usar ISO-8601 (`AAAA-MM-DD` o `AAAA-MM-DDThh:mm:ss`), sin `500` ni detalle interno

#### Scenario: El dataset pacientes ignora el período

- **GIVEN** el padrón completo del tenant con pacientes activos e inactivos
- **WHEN** el Dueño exporta `pacientes` sin rango y luego con `desde`/`hasta` que excluirían a la mayoría
- **THEN** las dos respuestas son `200` y contienen exactamente el mismo padrón completo

### Requirement: Enmascarado de identificadores en los textos libres de caja y liquidaciones

Los datasets `caja` y `liquidaciones` MUST reemplazar por `[dato oculto]` los DNI (7–8 dígitos con o sin puntos), CUIT/CUIL (11 dígitos con o sin guiones) y teléfonos (10–13 dígitos) que aparezcan en sus campos de texto libre (`concepto`, `observaciones`, `detalle`). El enmascarado MUST vivir en una función pura con tests propios. Los demás datasets conservan nombres y datos porque el destinatario es el Dueño.

#### Scenario: El concepto de caja se exporta enmascarado

- **GIVEN** un movimiento de caja con `concepto = "Seña DNI 30.123.456"` y otro con `concepto = "Seña turno"` en el período
- **WHEN** el Dueño exporta el dataset `caja` en CSV
- **THEN** el archivo muestra `Seña DNI [dato oculto]` en el primero, deja intacto el segundo y no aparece ningún DNI completo

#### Scenario: Las observaciones de liquidaciones se enmascaran

- **GIVEN** una liquidación con `observaciones = "CUIT 20-30123456-7 del afiliado"` y otra con `observaciones = "Presentada en término"`
- **WHEN** el Dueño exporta `liquidaciones` en CSV
- **THEN** la primera fila muestra `CUIT [dato oculto] del afiliado`, la segunda queda intacta y no aparece el CUIT completo

#### Scenario: Un teléfono escondido en detalle no sale en el archivo

- **GIVEN** un texto libre del dataset que contiene `+54 11 5555-1234`
- **WHEN** el Dueño exporta `caja` o `liquidaciones`
- **THEN** el archivo muestra `[dato oculto]` y no el número completo

### Requirement: Exportación asíncrona con descarga para volúmenes grandes

El sistema MUST contar las filas antes de generar: con `filas <= EXPORTACION_UMBRAL_FILAS` (default **5000**) responde el archivo directo; con `filas > umbral` MUST encolar un job y responder `202` con `job_id` y estado `pendiente`. El job MUST vencer a las **24 horas** (TTL fijo, sin variable de configuración) y ser visible solo para el Dueño del tenant. Un job en `error` MUST responder `409` genérico; uno vencido o sin archivo, `404` uniforme.

#### Scenario: El borde exacto del umbral responde directo

- **GIVEN** un período con exactamente 5000 filas (umbral default)
- **WHEN** el Dueño solicita la exportación
- **THEN** el sistema responde `200` con el archivo, no encola ningún job y no crea estado de job en Redis

#### Scenario: Una fila sobre el umbral encola un job

- **GIVEN** un período con 5001 filas
- **WHEN** el Dueño solicita la exportación
- **THEN** el sistema responde `202` con `job_id` y estado `pendiente`, y no devuelve el cuerpo del archivo

#### Scenario: Volumen alto encola un job y permite descargarlo al terminar

- **GIVEN** un período con más filas que el umbral configurado
- **WHEN** el Dueño solicita la exportación y luego de que el worker lo procesa consulta el estado
- **THEN** la primera respuesta es `202` con `job_id` y estado `pendiente`, el estado pasa a `listo` y la descarga devuelve el archivo generado

#### Scenario: Descarga antes de que el job esté listo

- **WHEN** el Dueño pide la descarga de un job que sigue `pendiente`, `en_cola` o `procesando`
- **THEN** el sistema responde `409` con un mensaje que indica esperar a que el job termine

#### Scenario: Worker que falla deja el job en error

- **GIVEN** un job encolado cuyo armado de archivo falla en el worker
- **WHEN** el Dueño consulta el estado y pide la descarga
- **THEN** el estado es `error` y la descarga responde `409` con un mensaje genérico (“no pudimos generar el archivo, probá de nuevo”), sin stack trace, sin detalle interno y sin PHI

#### Scenario: Job listo con archivo borrado responde como inexistente

- **GIVEN** un job en estado `listo` cuyo archivo ya fue borrado del disco
- **WHEN** el Dueño pide la descarga
- **THEN** el sistema responde `404` con el mismo cuerpo que para un job inexistente y sugiere volver a exportar

#### Scenario: Job de otro tenant o vencido no es accesible

- **WHEN** el Dueño del tenant A consulta o descarga un `job_id` del tenant B o un job vencido
- **THEN** el sistema responde `404` con el mismo mensaje que para un job inexistente, sin revelar datos del otro consultorio

### Requirement: Sin job cuando Redis no está disponible

Si Redis no responde al crear el job, el sistema MUST responder `503` con un mensaje rioplatense accionable y MUST NOT crear job, archivo ni evento de auditoría, porque el pedido no llegó a registrarse.

#### Scenario: Redis caído al pedir el export

- **GIVEN** Redis no responde
- **WHEN** el Dueño pide una exportación que por volumen correspondería a un job
- **THEN** el sistema responde `503`, no crea job, no crea evento de auditoría y no deja archivo en disco

### Requirement: Retención y purga de los artefactos de exportación

Los archivos exportados contienen PHI y MUST NOT quedar en disco después de vencer. El sistema MUST borrar todo archivo con más de **24 horas** al arrancar el worker, antes de crear cada job y en el barrido del loop del worker, y MUST borrar el archivo parcial si el job falla. Un job vencido MUST responder `404` aunque el archivo todavía no se haya barrido.

#### Scenario: El arranque del worker barre los archivos vencidos

- **GIVEN** un archivo de exportación sintético con antigüedad de 25 horas en el directorio de exportaciones
- **WHEN** el worker arranca
- **THEN** el archivo se elimina del disco antes de procesar cualquier job

#### Scenario: Un job vencido ya no se puede descargar

- **GIVEN** un job creado hace 25 horas
- **WHEN** el Dueño pide su descarga
- **THEN** el sistema responde `404` con el mismo cuerpo que para un job inexistente y el archivo se elimina en el siguiente barrido

#### Scenario: Un job que falla no deja archivo

- **GIVEN** un job que falla después de haber empezado a escribir el archivo
- **WHEN** el worker termina de manejarlo
- **THEN** el estado queda `error` y no queda ningún archivo parcial en el directorio de exportaciones

### Requirement: Orden entre auditoría y encolado del export asíncrono

En el modo asíncrono el evento `exportacion.solicitar` y el job en `pendiente` MUST quedar persistidos antes de exponer el `job_id`; el `RPUSH` MUST ocurrir después del commit. Si el encolado falla, el job MUST pasar a `error`, la respuesta MUST ser `503` y el evento MUST conservarse como registro del pedido. Un pedido repetido MUST generar dos eventos append-only y dos jobs independientes, y el worker MUST NOT volver a auditar. Todo archivo descargable MUST tener su evento y su job en `listo`.

#### Scenario: Exportación asíncrona deja su evento antes de exponer el job_id

- **WHEN** el Dueño pide una exportación que se encola
- **THEN** el evento `exportacion.solicitar` asociado al `job_id` ya está persistido cuando la respuesta `202` expone el `job_id`, con dataset, formato, filas y modo `asincronico`

#### Scenario: El fallo al encolar deja el evento y marca el job en error

- **GIVEN** el evento de auditoría y el job `pendiente` ya confirmados, y un Redis que falla en el `RPUSH`
- **WHEN** el Dueño pide la exportación asíncrona
- **THEN** el sistema responde `503`, el job queda en `error` y el evento de solicitud sigue existiendo

#### Scenario: Un pedido repetido genera dos eventos y dos jobs

- **WHEN** el Dueño pide dos veces la misma exportación sobre el umbral
- **THEN** quedan dos eventos append-only con `job_id` distintos y dos jobs independientes descargables, y el worker no agrega un segundo evento por el mismo job

### Requirement: Registro auditable de cada exportación sin PHI

Cada pedido de exportación MUST insertar un evento con dataset, formato, cantidad de filas y modo. En el modo directo MUST insertarse en la misma transacción antes de entregar el archivo; si la inserción falla, MUST NOT entregarse el archivo ni el paquete del paciente. El evento MUST NOT contener DNI, teléfono, nombre de paciente, contenido clínico, nombre de archivo ni nombre de adjunto, y los logs, URLs y nombres de archivo MUST NOT incluir PHI (`R9`).

#### Scenario: Exportación directa deja su evento de auditoría

- **WHEN** el Dueño descarga un dataset por respuesta directa
- **THEN** queda un evento `exportacion.solicitar` con el dataset, el formato, la cantidad de filas y el modo `directo`, sin datos de pacientes y sin el nombre del archivo

#### Scenario: Si falla la auditoría no se entrega el archivo

- **GIVEN** una falla al insertar el evento de auditoría
- **WHEN** el Dueño pide un export directo o el paquete de un paciente
- **THEN** el sistema responde `500` o `503` con un mensaje genérico, no entrega ningún archivo ni JSON y no deja registro parcial

#### Scenario: Logs y URLs sin PHI

- **WHEN** se ejecuta cualquier exportación o descarga de job
- **THEN** los logs de API y worker, las URLs y los nombres de archivo solo contienen identificadores opacos y metadatos, nunca DNI, teléfono, nombre de paciente ni contenido clínico

#### Scenario: El evento de auditoría del export no guarda PHI

- **GIVEN** una exportación de `caja` con un `concepto` que contiene un DNI sintético
- **WHEN** se inspecciona el evento `exportacion.solicitar` en el trail
- **THEN** `despues` solo tiene dataset, formato, filas y modo, y no contiene el DNI, el concepto, el nombre del archivo ni la ruta en disco

### Requirement: Página legal pública de privacidad y HCE

El sistema MUST publicar una página legal en `/privacidad`, accesible sin sesión, que informe el responsable del tratamiento, la finalidad, la base legal (Ley 25.326 de datos personales y Ley 26.529 de historia clínica), los derechos del titular y cómo ejercerlos, la retención mínima de 5 años y una vía de contacto. La página MUST NOT incluir datos de pacientes ni PHI y MUST ser accesible desde la reserva pública y el pie del shell interno.

#### Scenario: Acceso público sin sesión

- **WHEN** una persona sin sesión abre `/privacidad`
- **THEN** el sistema muestra la página legal completa, sin pedir login ni token

#### Scenario: Contenido legal mínimo

- **WHEN** se revisa el contenido de `/privacidad`
- **THEN** menciona Ley 25.326, Ley 26.529 (HCE), finalidad del tratamiento, derechos de acceso/rectificación/supresión, retención mínima de 5 años y el contacto para ejercerlos

#### Scenario: La página legal no expone datos de pacientes

- **WHEN** se inspecciona el HTML, las llamadas de red y el almacenamiento del navegador de `/privacidad`
- **THEN** no aparece ningún dato de paciente, PHI ni credencial, y la página no guarda información clínica en el navegador (`R6`, `R9`)

### Requirement: Pantalla del Dueño para auditar y exportar

El sistema MUST ofrecer una sección interna de auditoría visible solo para quien tiene permiso de lectura sobre `auditoria`, con filtros, tabla paginada por keyset, detalle de valores antes/después y panel de exportación de los cuatro datasets. La pantalla MUST NOT persistir el trail ni datos clínicos en el almacenamiento del navegador (`R6`).

#### Scenario: Dueño filtra y pagina el trail

- **WHEN** el Dueño entra a la sección de auditoría, aplica un filtro por entidad y actor y pide más resultados
- **THEN** la tabla muestra solo los eventos filtrados, conserva el orden descendente y agrega la página siguiente sin duplicar filas

#### Scenario: El período y los timestamps se muestran en ART

- **WHEN** el Dueño aplica un rango de fechas en el filtro
- **THEN** la pantalla muestra el período y cada `created_at` en `America/Argentina/Buenos_Aires` con leyenda de zona, y envía al backend fechas ISO-8601, no la hora del navegador

#### Scenario: Un evento sin actor o de usuario dado de baja no rompe la tabla

- **GIVEN** un evento con `actor_id` nulo y otro de un usuario dado de baja
- **WHEN** el Dueño abre la tabla de auditoría
- **THEN** la primera fila muestra “sistema” y la segunda “usuario inactivo”, sin error de render y sin datos inventados

#### Scenario: Recepción y Odontólogo no ven la sección

- **WHEN** un usuario con rol `recepcion` u `odontologo` inicia sesión
- **THEN** el menú no muestra la sección de auditoría y, si entra por URL directa, recibe el estado de permiso denegado sin datos del trail

#### Scenario: Exportación en 1 clic desde la pantalla

- **WHEN** el Dueño elige un dataset y un formato en el panel de exportación
- **THEN** la pantalla descarga el archivo si la respuesta es directa o muestra el progreso del job y habilita la descarga cuando está listo, sin pedir configuración adicional
