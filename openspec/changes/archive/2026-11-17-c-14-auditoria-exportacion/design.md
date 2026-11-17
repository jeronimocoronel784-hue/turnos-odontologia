# Design

## Context

Ver `proposal.md` — Why. El punto de partida real del repo:

- `app/domain/auditoria.py` define la tabla `auditoria` (`tenant_id`, `actor_id`, `accion`, `entidad`, `entidad_id`, `antes`, `despues`, `created_at`) con el índice `ix_auditoria_tenant_entidad (tenant_id, entidad, entidad_id, created_at)`.
- `app/application/auditoria.py` ya expone `registrar_auditoria(...)` y los módulos de agenda, clínica, pacientes, presupuestos, caja, Mercado Pago, lista de espera y liquidaciones ya lo invocan. **El trail ya se escribe; C-14 agrega lectura y exportación.**
- La migración `001_initial_tenant_usuario_auditoria.py` deja al rol `turnos_app` solo `SELECT` + `INSERT` sobre `auditoria`; `UPDATE`/`DELETE` fallan con `SQLSTATE 42501`. El test `tests/test_auditoria_appendonly.py` ya cubre la DB y se reutiliza.
- `app/api/security.py` resuelve `ActorAutenticado` con el `tenant_id` del token y `requiere(Recurso, Accion)` aplica la matriz de `app/domain/rbac.py`.
- `app/api/routers/liquidaciones.py` + `app/application/liquidaciones.py` (C-13) ya tienen el patrón de exportación en servidor: `Response` con bytes, `Content-Disposition` ASCII + `filename*` RFC 5987, `Cache-Control: no-store`, CSV UTF-8 con BOM y JSON con `Decimal` como string. C-14 reutiliza ese enfoque; no inventa otro.
- `app/domain/textos_libres.py` (C-13) ya detecta DNI y teléfono en textos libres al escribirlos (`parece_phi`, `PATRON_DNI`, `PATRON_TELEFONO`) y rechaza con `422`. C-14 **reutiliza esos patrones para enmascarar** al exportar, en vez de inventar otra regex (D12); la guarda de escritura no cubre filas anteriores a C-13 ni el `concepto` de caja que llega del request (`app/application/caja.py:724`).
- `app/shared/exceptions.py` ya tiene `SolicitudInvalida` (`400`) y `EntidadInvalida` (`422`) con mensajes rioplatenses y sin stack trace (`RN-GL-02`, `R9`): el rango de fechas del export usa `400` y los parámetros semánticos del trail siguen en `422` (D13).
- `docker-compose.yml` levanta `api` y `worker` como contenedores separados sobre la misma imagen, con Redis 7 y el worker escuchando `turnos:jobs` (`app/workers/main.py`, hoy solo `procesar_outbox`).
- `src/frontend/` es una PWA React/TS con `main.tsx` (rutas públicas + `/app`), `LayoutInterno.tsx` y espejo de la matriz en `shared/rbac.ts`.
- Restricciones duras: `R1`–`R13` de `AGENTS.md`; `R4` (tenant del token), `R6` (sin clínica en storage del navegador), `R7` (sin hard delete), `R9` (sin PHI en logs/URLs), `R11` (DB real, ≥2 casos por comportamiento), `R13` (fixtures sintéticos).

## Goals / Non-Goals

**Goals:**

- Un contrato de lectura estable, filtrable y paginado para el trail existente, sin migración y sin exponer el ORM.
- Exportación tenant-wide repetible y auditable de los cuatro datasets del Flujo 7, en CSV/JSON, con el servidor como única fuente de verdad.
- PHI minimizada en lo que se comparte: identificadores enmascarados en los textos libres de caja y liquidaciones, y nombre de archivo armado solo con dataset, período e identificador opaco (`RN-SE-02`, `R9`).
- Una ruta asíncrona simple que reuse el worker Redis existente, con estado y descarga, sin introducir una cola nueva.
- Inmutabilidad demostrable en dos capas (HTTP/RBAC y DB) y aislamiento de tenant con tests explícitos.
- Cumplimiento mínimo de `RN-SE-02`: página legal pública y paquete de datos del paciente.
- Cero regresiones en endpoints entregados: solo se agrega una ruta en pacientes y permisos nuevos.

**Non-Goals:**

- No se implementa un visor forense ni correlación de eventos; el trail se lee tal cual se escribe.
- No se agrega `ip` a `auditoria` (la KB lo menciona como nullable; el modelo actual no lo tiene y no hay migración).
- No se auditan las lecturas de historia clínica que hoy no lo hacen: se registra como deuda, no se implementa (`R7`, disciplina de alcance).
- No se implementa exportación parcial para Recepción/Odontólogo ni autoservicio del paciente por token; ambas quedan como consulta al PO. El desvío de la matriz de `03_actores_y_roles.md:32,34` se justifica en “Desvío respecto de la KB”, más abajo.
- No se agrega cifrado en reposo ni object storage para los archivos de exportación; el piloto es un solo nodo.
- No se toca el contrato de `GET /api/liquidaciones/{id}/exportar` (C-13) ni la matriz vigente del recurso `EXPORTACION`.

## Decisions

### Desvío respecto de la KB: solo el Dueño exporta

**La KB dice** (`knowledge-base/03_actores_y_roles.md:32`): “Exportación CSV/JSON | Sí | Parcial (agenda/caja + liquidaciones de obras sociales) | Parcial (clínica propia)”, y `03_actores_y_roles.md:34` agrega que el Odontólogo “nunca reabre cierres de caja ni exporta liquidaciones de obras sociales”. Es decir: la matriz le da exportación **parcial** a Recepción y a Odontólogo.

**C-14 hace algo más restrictivo**: el trail (`GET /api/auditoria`), los cuatro datasets (`GET /api/exportacion/{dataset}`) y el paquete del paciente (`GET /api/pacientes/{id}/exportar-datos`) quedan **solo Dueño**; Recepción y Odontólogo reciben `403` en los tres. Es un desvío consciente, no un olvido.

**Por qué**:

- `RN-SE-02` impone mínimo necesario y control de acceso por rol sobre datos de salud: el archivo exportado es un volcado completo del consultorio con DNI, teléfono, obra social y afiliado; el Dueño es el responsable del tratamiento.
- El destino real de estos archivos es un tercero (la contadora, el abogado, una obra social). Habilitar la exportación parcial a Recepción multiplica las copias de PHI fuera del sistema sin que exista hoy un mecanismo de scoping por fila (agenda/caja por usuario, clínica por profesional) en el exportador; implementarlo sería un filtrado nuevo, no un permiso.
- El riesgo de fuga al compartir un CSV con PHI es mayor que el beneficio operativo de un export parcial en el piloto de 1 consultorio.

**Consecuencia si el PO habilita la exportación parcial**: hay que (a) agregar scoping por actor al `SELECT` de `agenda`/`caja`/`clínica`, (b) sumar datasets/roles en el guard y en `shared/rbac.ts`, (c) reescribir los tests de la matriz de 3 roles de §2 y del spec, y (d) actualizar la fila 32 de `03_actores_y_roles.md` si la decisión es la contraria. El guard queda aislado en `requiere(Recurso.EXPORTACION_TENANT, Accion.EXPORTAR)` para que el rework no toque los routers. **No se edita `knowledge-base/`**: la pregunta va al PO (ver Open Questions) y el cambio de la KB lo hace el humano.

**Lo que NO se toca**: `Recurso.EXPORTACION` conserva su fila actual (`dueno`/`recepcion`/`odontologo` con `EXPORTAR`, `app/domain/rbac.py:90-94`) para no romper el contrato ya entregado de C-13 (`GET /api/liquidaciones/{id}/exportar`); C-14 usa un recurso nuevo para la exportación **completa del consultorio** (D3).

### D1 — Sin migración; índices evaluados y deuda explícita

Se lee la tabla existente con el índice `(tenant_id, entidad, entidad_id, created_at)` para el camino principal (entidad + id + período). Los filtros por actor o por rango sin entidad pueden recorrer el índice por `tenant_id` o hacer un scan acotado al tenant. Con el volumen del piloto (1 consultorio, estimación 50–200 eventos/día ⇒ 18k–73k filas/año) el scan es aceptable; agregar un índice exige migración y C-14 declara “sin migración”.

- **Deuda explícita**: si la tabla supera ~200k filas o el p95 de la consulta supera 300 ms medido con `EXPLAIN (ANALYZE, BUFFERS)`, agregar en un change posterior `ix_auditoria_tenant_created_at (tenant_id, created_at DESC)` e `ix_auditoria_tenant_actor_created_at (tenant_id, actor_id, created_at DESC)`. No se crean ahora.
- **Alternativa descartada**: crear los índices en C-14. Se descarta por la restricción de scope y porque el costo de escritura del trail (insert por cada mutación) no se justifica con el volumen actual.

### D2 — Contrato de `GET /api/auditoria`

- Query params: `entidad` (1–60), `entidad_id` (1–60), `accion` (1–60), `actor_id` (UUID), `desde`/`hasta` (ISO 8601; si falta offset se interpreta `America/Argentina/Buenos_Aires` y se normaliza a UTC antes de comparar), `limite` (1–200, default 50) y `cursor` (opaco, base64url de `{"created_at","id"}`).
- `desde` es inclusivo y `hasta` exclusivo. `desde > hasta` ⇒ `422` vía `EntidadInvalida` (mensaje rioplatense, `RN-GL-02`). Cursor inválido, corrupto o base64 mal codificado ⇒ `422`; no se ignora en silencio.
- Orden `created_at DESC, id DESC`; la página siguiente usa `(created_at, id) < (cursor.created_at, cursor.id)`. Por eso el cursor lleva **siempre los dos campos**: dos eventos con el mismo `created_at` se desempatan por `id` y la paginación no los duplica ni los saltea. Sin `OFFSET`.
- Respuesta `AuditoriaPaginaRead { eventos: list[AuditoriaEventoRead], siguiente_cursor: str | null }`. `AuditoriaEventoRead` expone `id`, `actor_id`, `accion`, `entidad`, `entidad_id`, `antes`, `despues`, `created_at`. No expone `tenant_id` (redundante) ni el ORM (`R1`).
- El `tenant_id` sale de `ActorAutenticado`; si llega `?tenant_id=...` se ignora y el filtro del token manda (`R4`). Hay un test que envía el tenant B y verifica que el resultado siga siendo del A.
- **Alternativa descartada**: paginación por `OFFSET` con `total`. Se descarta por costo en tablas que crecen y porque el cliente solo necesita “cargar más”.

### D3 — RBAC: recurso nuevo para la exportación tenant-wide

- `Recurso.AUDITORIA` queda como está: `dueno: SOLO_LECTURA`, `recepcion`/`odontologo`: `NINGUNO`.
- Se agrega `Recurso.EXPORTACION_TENANT` con `dueno: {EXPORTAR}` y `recepcion`/`odontologo`: `NINGUNO`, usado por `/api/exportacion/*`.
- La restricción cubre **los tres** caminos: trail (`AUDITORIA`), cuatro datasets (`EXPORTACION_TENANT`) y paquete del paciente (`PACIENTES.EXPORTAR`). Recepción y Odontólogo reciben `403` en cada uno (desvío de `03_actores_y_roles.md:32,34` documentado arriba); no hay export parcial en C-14.
- **Por qué no reutilizar `Recurso.EXPORTACION`**: esa fila es el espejo de la matriz de `03_actores_y_roles.md`, que da exportación **parcial** a Recepción (agenda/caja + liquidaciones OS) y Odontólogo (clínica propia). Cambiarla a “solo Dueño” contradiría la KB y rompería la semántica de una fila ya entregada aunque hoy no tenga endpoints. El recurso nuevo expresa la exportación **completa del consultorio**, que es la que C-14 restringe al Dueño.
- `Recurso.PACIENTES` suma `Accion.EXPORTAR` solo a Dueño. Recepción conserva CRUD (sin exportar el paquete), Odontólogo sigue en solo lectura. La UI refleja ambas matrices en `shared/rbac.ts`.
- **Alternativa descartada**: un guard ad-hoc por rol dentro del router. Se descarta porque rompe el patrón `requiere(...)` y deja la matriz y la API desincronizadas.

### D4 — Datasets, columnas y semántica del período

`GET /api/exportacion/{dataset}?formato=csv|json&desde=&hasta=`, con `dataset` como enum (`agenda`, `pacientes`, `caja`, `liquidaciones`). Columnas explícitas:

| Dataset | Filas y filtro | Columnas |
|---|---|---|
| `agenda` | Turnos con `inicio` en `[desde, hasta)` | `turno_id`, `inicio`, `fin`, `estado`, `prestacion`, `profesional`, `matricula`, `sillon`, `paciente_id`, `paciente_nombre`, `sobreturno` |
| `pacientes` | **Padrón completo** del tenant (activos e inactivos); **ignora** `desde`/`hasta` (documentado, no silencioso) | `paciente_id`, `nombre`, `dni`, `telefono`, `email`, `fecha_nac`, `obra_social`, `nro_afiliado`, `optin_wa`, `activo`, `created_at` |
| `caja` | Movimientos con `created_at` en `[desde, hasta)` | `movimiento_id`, `created_at`, `tipo`, `concepto` (enmascarado), `medio`, `monto`, `turno_id`, `cierre_id` |
| `liquidaciones` | Liquidaciones cuyo `periodo` cae en los meses del rango | `liquidacion_id`, `obra_social`, `periodo`, `estado`, `total`, `total_reconocido`, `turnos_sin_cobertura`, `observaciones` (enmascarada), `created_at` |

- **Lista cerrada**: estas columnas son el contrato del dataset y se verifican literales en los tests (orden y encabezados incluidos). Agregar una columna es un cambio de contrato, no un detalle de implementación.
- **`saldo_debito` no se exporta**: en `04_modelo_de_datos.md:124` es un campo derivado (`total - total_reconocido`), no una columna de `liquidacion_os`. El export de resumen no recalcula derivados: quien los necesite los obtiene de `total` y `total_reconocido`. El detalle con débitos sigue disponible por el export ya entregado de C-13 (`RN-OS-03`), que no se toca.
- **`observaciones` de liquidaciones sí se exporta, enmascarada**: es un `Text` libre del circuito de OS y puede traer un identificador; se aplica el mismo enmascarado que `concepto` (D12).
- Sin rango explícito, `agenda`, `caja` y `liquidaciones` usan el **mes calendario en curso** en `America/Argentina/Buenos_Aires`; `pacientes` exporta el padrón completo y no toma período (el spec lo declara y hay un escenario que compara la salida con y sin parámetros). El período se calcula en servidor (nunca en el cliente, `R8`).
- `agenda` no incluye DNI ni contenido clínico: el nombre alcanza para leer la agenda y el DNI vive en el dataset `pacientes` (mínimo necesario).
- Montos con `Decimal` y serialización string en JSON (`R8`). CSV UTF-8 con BOM, `,` y CRLF (mismo helper que C-13).
- **Nombre del archivo**: `exportacion-<dataset>-<yyyymmdd>[_<yyyymmdd>]-<opaco>.<ext>`, donde `opaco` es el `job_id` en el modo asíncrono o un `uuid4` de request en el directo. Solo dataset + período + identificador opaco: nunca DNI, nombre de paciente, teléfono ni tenant (`R9`).
- `Content-Disposition` + `filename*` RFC 5987 + `Cache-Control: no-store`, reutilizando el patrón de `ExportacionLiquidacion.cabeceras()`.
- **Alternativa descartada**: un endpoint por dataset (`/exportar/pacientes`, `/exportar/caja`...). Se descarta para no multiplicar contratos y poder compartir umbral, job y auditoría.

### D5 — “1 clic”, umbral y respuesta directa vs job

- “1 clic” significa: desde la pantalla de auditoría el Dueño elige dataset + formato y la aplicación inicia la descarga o el job sin pedir configuración adicional; la API recibe una única request `GET` y, si no hay rango, aplica el default del punto D4.
- Antes de generar, se ejecuta un `SELECT count(*)` con los mismos filtros. Si `filas ≤ EXPORTACION_UMBRAL_FILAS` (default **5000**, env, `ge=1`) se genera el archivo en memoria y se responde `200` con el cuerpo. Si supera el umbral se encola y se responde `202` con `ExportacionJobRead`.
- **El borde es el umbral mismo**: `filas = 5000` ⇒ `200` directo; `filas = 5001` ⇒ `202` con job. Se testea exacto con ambos valores (no “alrededor del umbral”).
- **Dataset vacío**: `0` filas ⇒ `200` con CSV de solo cabecera o JSON `[]`; no es `404` ni dispara job.
- **Por qué 5000**: un CSV de 5000 filas ronda <2 MB y se arma en menos de un segundo en memoria; queda lejos del timeout del proxy y del riesgo de memoria de la API. El umbral es configurable sin tocar código.
- El conteo se hace con el índice de tenant de cada tabla; no se trae el dataset para contarlo.
- **Alternativa descartada**: `StreamingResponse` siempre con corte a mitad de stream. No se puede cambiar de `200` a `202` una vez empezado el cuerpo, así que el conteo previo es necesario.

### D6 — Job asíncrono sobre el worker existente

- Se reutiliza la cola `turnos:jobs` y `procesar_job`; se agrega el tipo `exportar_dataset`. Payload: `job_id`, `tenant_id`, `actor_id`, `dataset`, `formato`, `desde`, `hasta`. Sin PHI.
- Estado en Redis, hash `exportacion:job:{tenant_id}:{job_id}`: `estado` (`pendiente|en_cola|procesando|listo|error`), `dataset`, `formato`, `filas`, `creado_at`, `expira_at`, `nombre_archivo`, `error` genérico. El namespace por tenant evita que un `job_id` de otro consultorio sea visible.
- **TTL fijo de 24 h, sin variable de entorno**: el hash y el archivo vencen juntos y el spec, el design y los tests dicen lo mismo. Configurarlo por consultorio queda como deuda (no hay caso de uso medido y un TTL mayor alarga la vida del PHI en disco); no se agrega `EXPORTACION_TTL_HORAS`.
- Archivo en `EXPORTACIONES_DIR` (default `/var/tmp/turnos-exportaciones`), nombre `{job_id}.{csv|json}`. `docker-compose.yml` monta el volumen nombrado `exportaciones` en `api` y `worker` (son contenedores distintos). No hay migración.
- **Orden del pedido asíncrono** (no se puede meter un `RPUSH` dentro de la transacción SQL):
  1. Antes del commit, en la misma unidad de trabajo: `INSERT` del evento `exportacion.solicitar` (`entidad_id=job_id`, `modo="asincronico"`) **y** el job en estado `pendiente`.
  2. `COMMIT`.
  3. `RPUSH` a `turnos:jobs` en pipeline.
  4. `202` con `job_id` y `estado=pendiente`.
- **Si falla Redis antes de registrar el job** (no se puede escribir el hash `pendiente`): se aborta la transacción, `503`, sin job y sin evento — no hubo pedido aceptado. **Si falla el `RPUSH` después del commit**: el job pasa a `estado=error`, se responde `503` y el evento de auditoría **queda**, que es lo correcto: registra que el Dueño pidió exportar y el sistema no pudo encolarlo. Un evento sin archivo no es una fuga de datos.
- **Contrato de integridad**: **sin archivos huérfanos** — todo archivo descargable tiene su evento de solicitud y su job en `listo`. No se promete “sin eventos huérfanos”: con una cola fuera de la transacción eso no se puede garantizar en los dos sentidos.
- `GET /api/exportacion/jobs/{job_id}` devuelve estado + `filas` + `expira_at`; `GET /api/exportacion/jobs/{job_id}/descarga` devuelve el archivo si `estado=listo` (`200`), `409` si sigue `pendiente|en_cola|procesando` **o si el job quedó en `error`** (“no pudimos generar el archivo, probá de nuevo”, sin detalle interno), y `404` uniforme si venció, es de otro tenant, no existe o el archivo ya no está.
- El worker marca `procesando`, arma el archivo con la misma función de aplicación que el camino directo, lo escribe y marca `listo`. Si falla, marca `error` con mensaje genérico (sin stack trace, sin PHI), **borra el archivo parcial en el `finally`** y no reintenta (deuda).
- **Purga de archivos con PHI**: `purgar_exportaciones_vencidas()` borra de `EXPORTACIONES_DIR` todo archivo con antigüedad mayor a 24 h. Se invoca **al arrancar el worker**, **antes de crear cada job** (en API y worker) y **en cada vuelta del loop del worker** con throttle a una vez cada 5 minutos (constante de módulo; el `brpop(timeout=2)` ya devuelve el control cuando no hay jobs). El hash de Redis expira solo. No se borra al descargar, para permitir reintentos dentro del TTL. Ningún archivo sobrevive más de 24 h más una vuelta de barrido.
- **Alternativas descartadas**: `BackgroundTasks` de FastAPI (no durable, se pierde al reiniciar y no es visible desde otro worker); cola nueva (Celery/RQ) (infra extra sin necesidad); guardar el archivo en Redis (memoria y valores grandes); hacer siempre síncrono (timeouts y memoria); guardar el estado del job en Postgres (exigiría migración y el archivo es efímero).

### D7 — Auditoría de cada exportación (sin PHI)

- `GET /api/exportacion/*` directo: inserta `accion="exportacion.solicitar"`, `entidad="exportacion"`, `entidad_id=<uuid de request>`, `despues={"dataset","formato","filas","modo":"directo"}` en la **misma transacción** (`registrar_auditoria` + `commit`), siguiendo el patrón de C-19.
- Asíncrono: el evento se inserta **antes de exponer el `job_id`**, con `entidad_id=job_id` y `modo="asincronico"`; el worker no vuelve a auditar para evitar duplicados. Si el `RPUSH` falla después del commit, el evento queda y el job queda `error` (D6): el trail registra un pedido que no llegó a encolarse, y eso es trazabilidad, no un archivo huérfano.
- Paquete del paciente: `accion="paciente.exportar_datos"`, `entidad="paciente"`, `entidad_id=<paciente_id>`, `despues={"formato":"json","secciones":[...]}`. Nunca guarda DNI, nombre, teléfono ni contenido clínico (`R9`, `RN-SE-01`).
- **Si la inserción de auditoría falla, no se entrega nada**: el export directo y el paquete abortan sin respuesta con archivo (`500` genérico, o `503` si la causa es la caída de la DB); el asíncrono ni siquiera crea el job. Todo o nada, `R7`.
- **Pedido repetido**: dos pedidos iguales generan **dos eventos append-only y dos jobs independientes**; no hay deduplicación por dataset/período. Cada acción del Dueño es un acto auditable y deduplicarla escondería un pedido real; el worker no emite un segundo evento por el mismo job.
- El evento **no** guarda el nombre del archivo, la ruta en disco ni el nombre de un adjunto clínico: solo dataset, formato, conteo de filas, modo y secciones.

### D8 — Exportación de datos del paciente (`RN-SE-02`)

- Ruta `GET /api/pacientes/{paciente_id}/exportar-datos` en `pacientes.py`, guard `requiere(Recurso.PACIENTES, Accion.EXPORTAR)` (solo Dueño). Formato **JSON** con envoltorio:

```
{ generado_at, consultorio: { nombre, slug }, paciente: {...},
  turnos: [...], ficha_clinica: {...}|null, evoluciones: [...],
  odontograma: { eventos: [...] }, presupuestos: [...],
  consentimientos: [...],
  adjuntos: { cantidad, items: [{ tipo, mime_type, tamano_bytes, created_at }] },
  movimientos: [...] }
```

- Alcance mínimo: identificación y contacto; turnos (fecha, estado, prestación, profesional, sillón); ficha clínica/anamnesis; evoluciones; eventos de odontograma; presupuestos con ítems y turnos vinculados; consentimientos (versión, hash de firma, fechas, canal, revocado); metadata de adjuntos **sin nombre de archivo**; movimientos de caja vinculados a sus turnos. Montos calculados/leídos en servidor (`R8`).
- **Adjuntos sin nombre**: el nombre original lo elige quien sube el archivo y puede traer PHI (“radiografia-juan-perez.jpg”). El paquete lleva cantidad, tipo, `mime_type`, tamaño y fecha, que alcanzan para ejercer el derecho de acceso sin reenviar un identificador en texto libre.
- **`firma_hash` se mantiene**: es un digest opaco de 64 caracteres que prueba que la firma existió y es verificable contra el texto; no revela el contenido clínico ni identifica a la persona. Sin él, el paquete no permite demostrar la integridad del consentimiento (que es justamente lo que el titular reclama). No se incluye `texto_contenido` completo.
- **Paciente sin actividad**: si el paciente existe pero no tiene turnos, ficha, evoluciones, consentimientos ni presupuestos, el paquete responde `200` con las listas vacías y `ficha_clinica: null`. El derecho de acceso no depende de que haya actividad; confundir “sin datos” con “no existe” sería un `404` incorrecto.
- **Paciente con prestación invasiva sin consentimiento firmado**: se exporta igual, con `consentimientos: []` o sin el firmado. `RN-CL-02` gatea la atención, no la entrega de datos al titular.
- Exclusiones explícitas: otros pacientes, trail de auditoría, tokens/credenciales, binarios de adjuntos, **nombres de archivos adjuntos** y datos internos del tenant.
- Todas las consultas filtran `tenant_id = actor.tenant_id` **y** `paciente_id`; un UUID ajeno o inexistente devuelve el mismo `404` (`NoEncontrado`), sin distinguir. El UUID es del servidor; no se busca por DNI ni por nombre, así que no hay enumeración.
- **Por qué solo Dueño**: la KB (`03`) no le da exportación de pacientes a Recepción ni a Odontólogo; el Dueño es el responsable del tratamiento y entrega el paquete al titular. En v1 el paciente no tiene cuenta ni token por paciente (`token_gestion` es por turno, `RN-SE-03`), así que el autoservicio requeriría un modelo/token nuevo. Se registra como consulta al PO, no se inventa.
- **Por qué JSON y no CSV**: el paquete es anidado (HC + evoluciones + odontograma + presupuestos); un CSV plano perdería estructura. Se deja CSV como deuda si el PO lo pide.

### D9 — Página legal pública

- Ruta pública `/privacidad` (React, `features/legal/PaginaLegalPage.tsx`), sin login, sin llamada a la API, con contenido versionado en el repo. Se enlaza desde `HomePage` y desde el pie de `LayoutInterno`.
- Secciones: responsable del tratamiento, finalidad, base legal (Ley 25.326 y Ley 26.529 de HCE), derechos de acceso/rectificación/supresión y cómo ejercerlos, retención mínima de 5 años (PO-03 abierta: se informa “mínimo 5 años, sujeto a dictamen”), contacto, ausencia de tracking y de datos de pacientes.
- El contacto sale de `VITE_CONTACTO_PRIVACIDAD` (build-time); si no está definido, el texto remite al consultorio donde se atendió el paciente, sin inventar un email.
- No hay PHI, ni datos de pacientes, ni llamadas de red con datos personales; no se escribe nada en `localStorage` (`R6`, `R9`).
- **Alternativa descartada**: endpoint backend que sirva el texto legal. Se descarta porque es contenido estático, no depende del tenant en v1 y evita superficie de ataque adicional.

### D10 — Pantalla interna del Dueño

- Ruta `/app/auditoria` y entrada de menú visibles solo si `permite(roles, "auditoria", "leer")`; Recepción/Odontólogo no ven la sección y, por URL directa, reciben el estado de permiso denegado sin datos (el backend igual responde `403`).
- Filtros: entidad (datalist con valores conocidos + texto libre), actor (select alimentado por `GET /api/usuarios`, que el Dueño puede leer), acción, rango de fechas. Tabla con fecha, actor, entidad, `entidad_id`, acción y `<details>` con el JSON de `antes`/`despues`. “Cargar más” usa `siguiente_cursor`.
- **Fechas en ART**: la tabla y el panel muestran el período y cada `created_at` en `America/Argentina/Buenos_Aires` (formato `dd/mm/aaaa hh:mm`), con leyenda de zona; el request viaja en ISO-8601 con offset y el usuario puede dejar las fechas sin offset (se interpretan en ART). No se usa la zona del navegador.
- **Actor ausente**: `actor_id` es nullable (`app/domain/auditoria.py:28`) y un usuario puede estar dado de baja. Si el evento no tiene actor, o el `actor_id` no aparece en la lista de usuarios, la celda muestra “sistema” / “usuario inactivo” y el render no se rompe.
- Panel de exportación: cuatro tarjetas (agenda, pacientes, caja, liquidaciones) con selector CSV/JSON y un botón. Respuesta `200` ⇒ descarga blob con el nombre del header; `202` ⇒ guarda `job_id` y consulta el estado cada 3 s (React Query) hasta `listo`, luego descarga; `409`/`404`/`403`/`5xx` ⇒ mensaje uniforme del backend (`RN-GL-02`).
- El trail y los archivos **no** se guardan en `localStorage`/`sessionStorage` (`R6`); el estado vive en memoria/React Query.
- En `PacienteDetallePage` se agrega “Exportar datos del paciente” visible solo con `permite(roles, "pacientes", "exportar")`, que descarga el JSON del punto D8.
- TypeScript estricto, sin `any` (`R5`); componentes en `PascalCase`; toda descarga usa `credentials` del cliente existente.

### D11 — Errores, seguridad y observabilidad

- `403` con el mensaje de `PermisoInsuficiente`; `404` uniforme para paciente/job ajeno, inexistente, vencido o con archivo ya borrado; `409` para descarga antes de tiempo o con job en `error`; `400` para el rango de fechas inválido del export (D13); `422` para dataset, formato o cursor inválidos; `503` si Redis no está disponible o si falla el encolado. Nunca stack traces (`R9`).
- Logs de API/worker solo con `job_id`, dataset, formato, filas y estado; nunca DNI, nombre, teléfono, `entidad_id` de paciente ni contenido del archivo.
- URLs sin PHI: la ruta del paciente usa UUID; los filtros del trail usan UUID/entidad/acción, nunca DNI/nombre/teléfono.
- Archivos `no-store`, sin token en URL, con nombre opaco y TTL; el Dueño los descarga autenticado contra el namespace de su tenant.

### D12 — Enmascarado de identificadores en textos libres (caja y liquidaciones)

- `MovimientoCaja.concepto` es `String(160)` libre cargado por Recepción (`app/domain/caja.py:170`, `app/application/caja.py:724`); `LiquidacionOS.observaciones` es `Text` libre del circuito de OS (`app/domain/liquidacion_os.py:121`). Cualquiera de los dos puede traer un DNI, un CUIT/CUIL o un teléfono, y el CSV de caja es justamente el archivo que se comparte con la contadora: afirmar que “caja no incluye datos del paciente” era falso.
- **Regla**: los exports de `caja` y `liquidaciones` **enmascaran** los identificadores detectados en `concepto`, `observaciones` y `detalle` (y en cualquier columna de texto libre que se agregue a esos dos datasets) reemplazándolos por `[dato oculto]`.
- **Patrones** (función pura en `app/shared/sanitizar_phi.py`, con tests unitarios propios):
  - DNI: 7 u 8 dígitos, con o sin puntos (`30123456`, `30.123.456`, `3.012.345`).
  - CUIT/CUIL: 11 dígitos, con o sin guiones (`20301234567`, `20-30123456-7`).
  - Teléfono: 10 a 13 dígitos, con o sin `+`, espacios o guiones (`+54 11 5555-1234`, `1155551234`).
  - Reutiliza y extiende `PATRON_DNI`/`PATRON_TELEFONO` de `app/domain/textos_libres.py` (C-13) para no tener dos regex divergentes; la guarda de escritura sigue rechazando PHI nuevo, esto cubre las filas históricas y el `concepto`.
- **Alcance**: `pacientes`, `agenda` y el paquete clínico **conservan** nombres y datos porque el destinatario es el Dueño y es su propia base (el derecho de acceso exige entregarlos); lo que no puede pasar en ningún caso es PHI en el **nombre del archivo**, en la URL, en logs, en el cuerpo de errores ni en el evento de auditoría (D4, D7, D11).
- **Alternativa descartada**: excluir `concepto` del dataset. Se descarta porque el concepto es la única descripción del movimiento y sin él el CSV no sirve para conciliar; se enmascara el identificador y se conserva el texto útil.
- **Límite conocido**: una regex no detecta un nombre suelto (“Seña de Juan”). Se documenta como riesgo residual; la solución de fondo es estructurar caja (paciente y motivo como columnas) en otro change, no un detector de nombres.

### D13 — Validación del rango de fechas del export

- `desde <= hasta`, `hasta <= ahora` y **rango máximo de 366 días**. `desde` inclusivo, `hasta` exclusivo, ambos ISO-8601; sin offset se interpretan en `America/Argentina/Buenos_Aires` y se normalizan a UTC antes de consultar.
- Toda violación (rango invertido, `hasta` futuro, rango de más de 366 días, fecha mal formada) responde **`400`** con `SolicitudInvalida` y un mensaje rioplatense accionable que dice qué corregir (`RN-GL-02`), nunca `500` ni un `422` de Pydantic con el payload crudo.
- **Por qué 366 días**: cubre un año calendario completo (incluido el año bisiesto) para exportar el ejercicio, y acota el `count(*)`, el job y la memoria del worker. Un rango mayor es un volcado histórico que debe pedirse por partes.
- `dataset=pacientes` no toma período: si llegan `desde`/`hasta` se ignoran **de forma documentada** (el spec lo declara y el test compara la salida con y sin parámetros), no se rechaza, para que el botón de 1 clic no falle según el dataset elegido.
- **Alternativa descartada**: tope de 31 días. Se descarta porque impide exportar el año para la contadora, que es el caso de uso principal.

## Risks / Trade-offs

- **Consulta del trail sin índice por actor/fecha** → scan acotado al tenant; con el volumen del piloto es aceptable. Mitigación: medir con `EXPLAIN (ANALYZE, BUFFERS)` y agregar índices en un change posterior si se supera el umbral de D1 (deuda explícita).
- **El `count(*)` previo agrega una consulta por exportación** → se ejecuta sobre índices de tenant y rango; si el dataset es enorme, el costo es menor que generarlo. Si molesta, se puede cachear/estimar por tabla en un change posterior.
- **Worker caído o job descartado** → el estado puede quedar `pendiente`/`en_cola`/`procesando` hasta el TTL de 24 h. Mitigación: TTL fijo, reintento manual desde la pantalla y `error` visible; reintentos con backoff son deuda.
- **Archivos en disco local y volumen compartido** → funciona en el Compose de un nodo; en multi-instancia/multi-host requiere object storage. Mitigación: documentado como deuda; el piloto es mono-nodo.
- **Memoria del worker al armar archivos muy grandes** → el worker arma el archivo en memoria; el umbral deriva a async pero el rango máximo de 366 días (D13) acota el volumen. Mitigación: monitorear y, si hace falta, pasar a escritura incremental a disco en un change posterior (deuda).
- **PHI en archivos exportados** → es un flujo autorizado al Dueño (responsable del tratamiento), no un log. Mitigación: solo Dueño, `no-store`, TTL fijo, sin token en URL, nombre opaco, enmascarado de identificadores en los datasets que se comparten con terceros (D12) y auditoría del pedido. Cifrado en reposo queda como deuda.
- **La regex de enmascarado no detecta nombres sueltos** en `concepto`/`observaciones` (“Seña de Juan”) → riesgo residual aceptado: no se puede distinguir un nombre de una palabra cualquiera sin falsos positivos. Mitigación: enmascarado de identificadores numéricos, guía al usuario, y la solución de fondo es estructurar caja (paciente/motivo como columnas) en otro change.
- **Desvío de la matriz de roles de la KB** → si el PO habilita export parcial para Recepción/Odontólogo, hay que agregar scoping por actor y reescribir la matriz y sus tests. Mitigación: guard aislado en una dependencia, desvío documentado y pregunta abierta al PO (ver arriba); la KB no se edita desde C-14.
- **La auditoría existente puede contener snapshots con PHI** en `antes`/`despues` de otros módulos → la lectura es solo Dueño y nunca se loguea; revisar la minimización de esos snapshots es deuda fuera de C-14.
- **Texto legal genérico** → el contacto y la retención exacta dependen del consultorio y de PO-03. Mitigación: contenido versionado, revisión humana/legal antes de publicar, y texto que no promete plazos cerrados.
- **Lecturas clínicas no auditadas** → C-14 audita solo exportaciones y pedidos del paquete; no centraliza la auditoría de lecturas de HC. Se anota como deuda para no ampliar el alcance.
- **Descarga de job y archivo ya borrado** → `listo` en Redis pero archivo ausente por barrido o borrado manual: responder `404` uniforme, igual que un job inexistente, y ofrecer reintentar la exportación (test de borde).
- **Purga entre vencimiento y barrido** → el archivo puede sobrevivir hasta 24 h más una vuelta de barrido (máximo 5 min); un barrido más fino exigiría un cron o un `fsnotify`, deuda innecesaria para el piloto.

## Migration Plan

1. Desplegar backend + worker + frontend con el volumen `exportaciones` y las variables nuevas (`EXPORTACIONES_DIR`, `EXPORTACION_UMBRAL_FILAS`, `VITE_CONTACTO_PRIVACIDAD`); sin `alembic upgrade` (no hay revisión nueva). El TTL de los jobs es fijo de 24 h y no se configura por entorno.
2. Verificar `GET /api/auditoria` con el Dueño y `403` con Recepción; correr un export chico (directo) y uno sobre el umbral (job) con datos de seed.
3. Rollback: volver a la imagen anterior y quitar el volumen; no hay cambios de esquema. Los eventos de auditoría ya escritos quedan (append-only) y los jobs en Redis expiran solos. Los archivos del volumen se pueden descartar.

## Open Questions

- **Lista para el PO (no se edita la KB desde C-14)**: ¿Recepción y Odontólogo deben tener exportación parcial desde el exportador central, como dice `knowledge-base/03_actores_y_roles.md:32` (Recepción: agenda/caja + liquidaciones de OS; Odontólogo: clínica propia)? C-14 entrega todo solo al Dueño por mínimo necesario (`RN-SE-02`) y riesgo de fuga al compartir archivos con terceros; decisor: Dueño. Si la respuesta es sí, aplica un change posterior con scoping por actor y hay que actualizar la fila 32 de `03`.
- ¿El Dueño puede exportar el padrón completo de pacientes sin período? D13 lo deja así (el derecho de acceso y la contabilidad lo necesitan), pero es un volcado masivo de PHI a un archivo: si el PO quiere exigir rango, se cambia el contrato del dataset `pacientes`.
- ¿Se requiere autoservicio del paciente para descargar sus datos? Implicaría un token por paciente (nuevo modelo/migración) y hoy no existe; C-14 lo resuelve vía Dueño.
- ¿El plazo legal exacto de retención sigue siendo 5 años (PO-03)? La página legal informa “mínimo 5 años, sujeto a dictamen”.
- ¿El Dueño necesita ver el nombre/email del actor en el trail (join con `usuarios`) o alcanza `actor_id`? v1 muestra `actor_id` y “sistema” cuando falta; si se pide denormalizar, es un cambio de contrato posterior.
