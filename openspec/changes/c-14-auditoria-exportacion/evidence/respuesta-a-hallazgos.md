# Respuesta a los hallazgos del gate `sdd-change-review`

**Change**: `c-14-auditoria-exportacion` · **Fecha**: 2026-11-17
**Reporte origen**: `evidence/reporte-sdd-change-review.md` (veredicto: APROBAR CON CAMBIOS — 2 HIGH, 6 MEDIUM, 6 LOW)
**Alcance de esta corrección**: solo artefactos de planificación (`proposal.md`, `design.md`, `specs/**`, `tasks.md`). No se implementó código, no se tocó `knowledge-base/`, `AGENTS.md` ni `CHANGES.md`.

## Tabla de trazabilidad

| # | Sev. | Estado | Qué cambió (archivo:línea) | Escenario / tarea que lo cubre |
|---|------|--------|----------------------------|-------------------------------|
| 1 | HIGH | **CORREGIDO CON DECISIÓN** (consulta al PO abierta) | `design.md:41-55` nueva sección “Desvío respecto de la KB” con la cita `03_actores_y_roles.md:32,34`, argumento de mínimo necesario (`RN-SE-02`), riesgo de compartir archivos con terceros y consecuencia/rework; `design.md:35` (non-goal), `design.md:75-77` (D3), `design.md:219` (riesgo), `design.md:234` (pregunta al PO); `proposal.md:11` y `proposal.md:36-41` (Impacto → Riesgos y consultas al PO) | `specs/auditoria-exportacion/spec.md:52-83`: requisito “solo Dueño” y 6 escenarios (Dueño en los tres caminos, Recepción trail, Recepción 4 datasets CSV+JSON, Odontólogo trail, Odontólogo 4 datasets, Recepción/Odontólogo paquete); `specs/pacientes/spec.md:5-28`; `tasks.md:16` (2.5) |
| 2 | HIGH | **CORREGIDO** | `design.md:189-200` D12 (regla, patrones DNI/CUIT/CUIL/teléfono, `[dato oculto]`, función pura en `app/shared/sanitizar_phi.py`, reutiliza `app/domain/textos_libres.py`); `design.md:90-91` (columnas `concepto`/`observaciones` enmascaradas); `design.md:99` (nombre de archivo sin PHI); `design.md:218` (riesgo residual de regex) | `spec.md:219-236`: requisito de enmascarado + 3 escenarios (concepto con DNI, observaciones con CUIT, teléfono); `spec.md:146` (nombre de archivo sin datos del paciente); `spec.md:357` (evento sin PHI); `tasks.md:26-27` (4.1/4.2), `tasks.md:29` (4.4), `tasks.md:33` (4.8) |
| 3 | MEDIUM | **CORREGIDO** | `design.md:119-125` orden explícito evento+job `pendiente` → commit → `RPUSH` → `202`; fallo de `RPUSH` ⇒ job `error`, `503`, el evento queda; contrato reemplazado por “sin archivos huérfanos”; `design.md:131-138` D7; `design.md:126` (409/404) | `spec.md:317-334`: requisito “Orden entre auditoría y encolado” + escenarios (evento antes del `job_id`, fallo de encolado, pedido repetido); `tasks.md:39` (5.3), `tasks.md:42` (5.6) |
| 4 | MEDIUM | **CORREGIDO** | `design.md:202-208` D13 (`desde <= hasta`, `hasta <= ahora`, máximo 366 días, ISO-8601/ART, `400` con `SolicitudInvalida`); `design.md:96` (pacientes ignora período, documentado); `design.md:11` (reutiliza `SolicitudInvalida`) | `spec.md:189-217`: requisito de validación + 5 escenarios (rango invertido, `hasta` futuro, 400 días, fecha mal formada, pacientes ignora período); `tasks.md:31` (4.6); UI en ART: `spec.md:391-394`, `tasks.md:58` (7.5) |
| 5 | MEDIUM | **CORREGIDO** | `design.md:107-108` (borde exacto 5000/5001 y dataset vacío); `design.md:126` (`error` ⇒ 409, vencido/sin archivo ⇒ 404); `design.md:121` (Redis caído ⇒ sin job ni evento) | `spec.md:251` (5001 ⇒ job), `spec.md:245` (5000 ⇒ directo), `spec.md:268` (worker falla ⇒ `error` + 409 genérico), `spec.md:274` (job `listo` sin archivo ⇒ 404), `spec.md:289` (Redis caído ⇒ 503 sin job); `tasks.md:37` (5.1) |
| 6 | MEDIUM | **CORREGIDO CON DECISIÓN** | TTL **fijo de 24 h** sin variable: `design.md:117`, `design.md:128`, `design.md:228`; `proposal.md:31` (settings sin TTL) y `proposal.md:41` (deuda justificada); `tasks.md:38` (5.2 pide verificar que no existe variable de TTL) y `tasks.md:71` (9.2) | `spec.md:243` (requisito asíncrono: 24 h, TTL fijo, sin configuración) y `spec.md:299-314` (purga/vencimiento); ya no hay contradicción spec ↔ design |
| 7 | MEDIUM | **CORREGIDO** | `design.md:156-157` D8 (paciente sin actividad ⇒ 200 con listas vacías; invasiva sin consentimiento se exporta igual) | `specs/pacientes/spec.md:58-68`: escenarios “Paciente sin actividad recibe el paquete vacío” y “prestación invasiva sin consentimiento se exporta igual”; `tasks.md:47` (6.1) |
| 8 | MEDIUM | **CORREGIDO** | `design.md:128` D6: `purgar_exportaciones_vencidas()` al arrancar el worker, antes de crear cada job y en el loop idle con throttle de 5 min; borrado del archivo parcial en `finally` (`design.md:127`); retención máxima 24 h + una vuelta de barrido (`design.md:221`) | `spec.md:295-314`: nuevo requisito “Retención y purga de los artefactos de exportación” + 3 escenarios (barrido al arrancar, job vencido ⇒ 404, job fallido sin archivo); `tasks.md:41` (5.5, test `test_exportacion_purga.py`), `tasks.md:40` (5.4) |
| 9 | LOW | **CORREGIDO** | `design.md:47-49` (cursor `(created_at, id)`, orden con desempate, cursor corrupto ⇒ 422); `tasks.md:5` (1.1) y `tasks.md:7` (1.3) | `spec.md:25-34`: escenarios “keyset con `created_at` empatados” y “cursor corrupto se rechaza” |
| 10 | LOW | **CORREGIDO** | `design.md:135-138` D7 (fallo de auditoría ⇒ no se entrega nada; pedido repetido ⇒ 2 eventos y 2 jobs; el worker no audita dos veces) | `spec.md:346` (“Si falla la auditoría no se entrega el archivo”), `spec.md:332` (“Un pedido repetido genera dos eventos y dos jobs”); `specs/pacientes/spec.md:89-97`; `tasks.md:32` (4.7), `tasks.md:42` (5.6), `tasks.md:47` (6.1) |
| 11 | LOW | **CORREGIDO** | `design.md:93-95` (lista cerrada) | `spec.md:161-187`: dos requisitos con las columnas exactas de `agenda`/`pacientes` y `caja`/`liquidaciones` + escenarios de cabecera; `tasks.md:28` (4.3) |
| 12 | LOW | **CORREGIDO** | `design.md:47` (normalización ART→UTC del trail) | `spec.md:36-39`: escenario “Fechas sin offset se interpretan en ART”; `tasks.md:5` (1.1), `tasks.md:7` (1.3) y `tasks.md:58` (7.5) |
| 13 | LOW | **CORREGIDO** | `design.md:94`: `saldo_debito` no se exporta por derivado (`04_modelo_de_datos.md:124`); se obtiene de `total`/`total_reconocido` y el detalle sigue en C-13 | `spec.md:175-187` (requisito y escenario “Cabecera exacta de liquidaciones sin el derivado”); `tasks.md:28` (4.3 exige cabeceras sin `saldo_debito`) |
| 14 | LOW | **CORREGIDO** | `design.md:154-155` (adjuntos sin nombre, `firma_hash` justificado como digest opaco); `design.md:173-175` (UI: actor nulo ⇒ “sistema”, ART); `design.md:136-137` (el evento no guarda nombre de archivo) | `specs/pacientes/spec.md:46-56` (adjuntos sin nombre, `firma_hash` sí / `texto_contenido` no), `specs/pacientes/spec.md:99` (nombre de archivo opaco); `spec.md:396` (actor nulo/inactivo); `tasks.md:47` (6.1), `tasks.md:58` (7.5) |

## Decisiones tomadas

1. **Solo el Dueño exporta** (H1). Trail, los cuatro datasets y el paquete del paciente quedan Dueño-only; Recepción y Odontólogo reciben `403` en los tres caminos. Es un desvío consciente de `knowledge-base/03_actores_y_roles.md:32,34`, justificado por mínimo necesario (`RN-SE-02`) y por el riesgo de fuga de PHI en archivos que se comparten con terceros (contadora). No se toca la KB: la pregunta queda abierta para el PO y el rework, si habilita export parcial, está acotado al guard y a los tests de matriz.
2. **Textos libres de caja y liquidaciones se enmascaran** (H2). No se elimina `concepto`: se reemplazan DNI, CUIT/CUIL y teléfonos por `[dato oculto]`. Los datasets con PHI legítima (pacientes/agenda/clínica) conservan los datos porque el destinatario es el Dueño, responsable del tratamiento.
3. **Orden asíncrono**: evento de auditoría + job `pendiente` antes del commit, `RPUSH` después. Si el encolado falla, el evento se conserva (registra el pedido) y el job queda `error`. El contrato pasa de “sin eventos huérfanos” (imposible) a “sin archivos huérfanos”.
4. **TTL fijo de 24 h** (H6). Sin variable de entorno; la configurabilidad queda como deuda con motivo (no hay caso de uso medido y alarga la vida del PHI en disco).
5. **Rango de fechas del export**: máximo 366 días, `hasta` no futuro, `400` accionable. `pacientes` ignora el período de forma documentada y testeada.
6. **`dataset=pacientes` con `desde`/`hasta`**: se ignora explícitamente (no se rechaza) para no romper el botón de 1 clic; la salida debe ser idéntica con y sin parámetros.
7. **`firma_hash` se mantiene** en el paquete: es un digest opaco que prueba la firma; `texto_contenido` se excluye. **Nombres de adjuntos se excluyen** (pueden contener PHI); se informan cantidad, tipo/mime, tamaño y fecha.

## Consultas al PO que quedan abiertas

- **Exportación parcial para Recepción/Odontólogo** (H1): `03_actores_y_roles.md:32,34` la contempla; C-14 no la entrega. Decisor: Dueño. Si se habilita, requiere scoping por actor, cambio del guard, reescritura de la matriz y de los tests, y actualización de la fila 32 de `03` (la hace el humano, no C-14). Escalado al PO, no resuelto acá.
- **Padrón completo de pacientes sin período**: es un volcado masivo de PHI a un archivo; confirmar si se exige rango o justificación.
- **Autoservicio del paciente** para descargar sus datos: hoy lo entrega el Dueño; un token por paciente implicaría modelo/migración en otro change.
- **PO-03 (retención legal exacta)**: la página legal informa “mínimo 5 años, sujeto a dictamen”.
- **Trail con `actor_id` vs nombre/email**: v1 muestra `actor_id` y resuelve contra `/api/usuarios`; denormalizar es cambio de contrato posterior.
- **Revisión legal del texto de `/privacidad`**: quién firma el contenido y qué pasa si `VITE_CONTACTO_PRIVACIDAD` no está definido.

## Notas de coherencia

- **Nombre del evento**: se mantiene `exportacion.solicitar` (convención `<entidad>.<infinitivo>` del trail: `caja.registrar_movimiento`, `turno.cambiar_estado`); el contrato corregido de H3 cambia el **orden**, no el nombre.
- **Estado inicial del job**: `pendiente` (antes `en_cola`); `en_cola` queda como estado intermedio y la descarga responde `409` en `pendiente|en_cola|procesando|error`, `404` en vencido/ajeno/sin archivo.
- **Numeración de tareas**: se conservó la estructura de secciones 1–10 de `tasks.md`; las tareas nuevas se integraron en las secciones existentes (4.1–4.8, 5.1–5.7, 6.1–6.4, 7.1–7.7, 9.1–9.4).

## Conteos antes / después

| Artefacto | Antes | Después |
|---|---|---|
| `specs/auditoria-exportacion/spec.md` | 9 requisitos · 30 escenarios | 16 requisitos · 63 escenarios |
| `specs/pacientes/spec.md` | 3 requisitos · 9 escenarios | 4 requisitos · 15 escenarios |
| `tasks.md` | 42 tareas | 49 tareas |

## Verificación

- `openspec validate c-14-auditoria-exportacion --strict` → **valid** (verde).
- `openspec status --change "c-14-auditoria-exportacion" --json` → `proposal`, `specs`, `design`, `tasks` en `done`; `isPlanningComplete: true`.
- Sin PHI real, credenciales ni `.env` en los artefactos; los ejemplos usan DNI/CUIT/teléfonos sintéticos (`R9`, `R13`).
