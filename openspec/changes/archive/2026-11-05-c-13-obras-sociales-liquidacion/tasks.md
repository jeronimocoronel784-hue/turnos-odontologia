# Tasks: `c-13-obras-sociales-liquidacion`

> Strict TDD en todas las tareas: primero el test que falla (RED), después el mínimo código para pasarlo (GREEN), luego los casos borde que triangulan y recién al final el refactor. No marcar ninguna tarea como completada en esta propuesta.

## 1. Resolución de cobertura compartida (`D1`, `D2`, `RN-OS-01`)

- [x] 1.1 **Función pura de resolución de cobertura con `EstadoArancel`** (TDD)
  - Crear en `src/backend/app/domain/cobertura_os.py` el enum `EstadoArancel` (`vigente`, `vencido`, `sin_cobertura`), el dataclass `ResolucionCobertura` (`cobertura_id`, `arancel`, `cobertura`, `monto_a_cargo`, `estado_arancel`, `vigencia_desde`, `vigencia_hasta`, `advertencia`) y `resolver_cobertura_desde_candidatas(...)` con la regla de D2 (vigente → último arancel con `vigencia_desde` más reciente → particular).
  - Verificar con `tests/test_cobertura_resolucion.py`: cobertura vigente aplica `min(precio, arancel)`; sin convenio → particular; arancel vencido → usa el último arancel con advertencia; cobertura futura → particular con advertencia; `cantidad > 1` multiplica cobertura y a cargo.

- [x] 1.2 **Loaders async de cobertura y adaptadores de `C-10`/`C-11` sin cambio de contrato** (TDD)
  - Crear `src/backend/app/application/cobertura.py` con `resolver_cobertura_prestacion` (una prestación) y `resolver_coberturas_lote` (varias prestaciones en una sola query, sin N+1). Reemplazar el cuerpo de `calcular_montos_item_presupuesto` (`application/presupuestos.py`) por una delegación que conserve firma y tupla de retorno; `calcular_liquidacion_turno` (`application/caja.py`) queda intacta salvo el import.
  - Verificar con `tests/test_cobertura_servicio.py` (DB real en contenedor, `R11`): lookup por `obra_social` case-insensitive, aislamiento por `tenant_id`, y lote con 2 prestaciones devolviendo el mismo resultado que el lookup individual.
  - No-regresión obligatoria: `tests/test_presupuestos_negocio.py` y `tests/test_caja_negocio.py` deben pasar **sin modificaciones**.

- [x] 1.3 **Endpoint de lookup `GET /api/os/cobertura`** (TDD)
  - Crear `src/backend/app/api/schemas_liquidaciones.py` con `CoberturaLookupRead` (montos como `Decimal` serializado a string, sin PHI) y registrar el handler en el router de liquidaciones con `requiere(Recurso.LIQUIDACIONES, Accion.LEER)`; soportar `turno_id` (deriva prestación y fecha del turno) y `fecha` de referencia.
  - Verificar con `tests/test_os_cobertura_api.py`: respuesta completa en modo vigente, modo particular, `arancel_vencido = true` con advertencia; `404` para prestación de otro tenant; `422` si `turno_id` y `prestacion_id` se contradicen; `403` sin token.

## 2. Modelo de datos, migración y schemas

- [x] 2.1 **Dominio `liquidacion_os.py`: enums, grafo de estados y helpers de período** (TDD)
  - Crear `src/backend/app/domain/liquidacion_os.py` con `EstadoLiquidacionOS` (`borrador`, `presentada`, `pagada`, `con_debitos`, `anulada`), `es_transicion_liquidacion_valida` (grafo de D4) y `periodo_valido` / `periodo_desde_fecha` / `rango_periodo` (rango UTC semiabierto).
  - Verificar con `tests/test_liquidacion_os_dominio.py`: transiciones permitidas y rechazadas (incluye `presentada → anulada` inválida y estados terminales); `periodo_desde_fecha(date(2026, 11, 30)) == "202611"`; `rango_periodo("202611")` cubre del 01/11 al 01/12 exclusivo; períodos inválidos (`"20261"`, `"202613"`, `"abc"`) rechazados.

- [x] 2.2 **Modelos `LiquidacionOS` / `LiquidacionOSDetalle` y migración reversible `012_obras_sociales_liquidacion`** (TDD)
  - Definir los modelos con `TenantMixin`/`AuditMixin`, columnas, `CheckConstraint` e índices únicos parciales de D3/D6 en `liquidacion_os.py`.
  - Crear `src/backend/alembic/versions/012_obras_sociales_liquidacion.py` (`down_revision = "011_mercadopago_webhooks"`) con tablas, constraints, índices parciales, `GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE liquidacion_os, liquidacion_detalle TO turnos_app` y `REVOKE` en `downgrade`.
  - Registrar los modelos en `src/backend/alembic/env.py` y `tests/conftest.py` (import + limpieza en orden inverso a las FK).
  - Verificar con `tests/test_migracion_012_obras_sociales_liquidacion.py`: columnas e índices esperados; que la DB rechace `estado` inválido, `periodo` de largo distinto de 6, `monto_reconocido > monto_reclamado` y débito sin motivo; round-trip `upgrade head` → `downgrade 011_mercadopago_webhooks` → `upgrade head` en SQLite; presencia de los strings de `GRANT`/`REVOKE`.

- [x] 2.3 **Schemas Pydantic v2 de liquidaciones (`R1`, `R8`)** (TDD)
  - En `src/backend/app/api/schemas_liquidaciones.py`: `LiquidacionOSCreate` (`obra_social` 1..160, `periodo` con regex `^\d{6}$`), `LiquidacionOSDebitosInput`, `ResultadoOSInput` (`resultado` debe ser `pagada`/`con_debitos`), `LiquidacionOSAnularInput` (`motivo` obligatorio), `LiquidacionOSRead`, `LiquidacionOSDetalleRead` y `BORRADOR` de exportación. Todos los inputs con `extra='forbid'` y sin campos de totales calculados.
  - Verificar con `tests/test_schemas_liquidaciones.py`: rechazo de campos extra, `periodo` inválido, `monto_reconocido` negativo o con más de 2 decimales, débito sin motivo, motivo de anulación vacío y serialización de `Decimal` como string.

## 3. Casos de uso de la liquidación

- [x] 3.1 **Alta del borrador coleccionando turnos `finalizado` del período** (TDD)
  - Implementar `generar_borrador` en `src/backend/app/application/liquidaciones.py`: buscar turnos `finalizado` con `inicio` en el rango del período, resolver cobertura en lote (D1), incluir sólo prestaciones con convenio de la OS, calcular `monto_reclamado` y `total`, devolver `turnos_sin_cobertura` y `advertencias`.
  - Verificar con `tests/test_liquidaciones_negocio.py`: incluye sólo los finalizados del período; excluye `pendiente`/`confirmado`/`presente`/`cancelado`/`ausente`/`reprogramado`; excluye turnos de otro período; informa turnos sin cobertura; `422` sin turnos; `409` si ya existe borrador de la misma OS/período; `404` para prestaciones/turnos de otro tenant.

- [x] 3.2 **Registro de débitos sobre el borrador y recálculo de totales** (TDD)
  - Implementar `registrar_debitos`: validar estado `borrador`, exigir `debito_motivo` cuando hay recorte, actualizar `monto_reconocido` por `turno_id`, recalcular `total` y `total_reconocido` en servidor y auditar (`accion="liquidacion.debitos"`, `RN-SE-01`).
  - Verificar con `tests/test_liquidaciones_negocio.py`: débito con motivo actualiza totales y deja evento de auditoría sin identificadores de paciente; débito sin motivo → `422`; `monto_reconocido` mayor al reclamado → `422`; edición sobre `presentada` → `409`.

- [x] 3.3 **Presentación del borrador y registro del resultado de la OS** (TDD)
  - Implementar `presentar_liquidacion` (`borrador → presentada`, exige ≥1 turno y fija `presentada_por`/`presentada_at`) y `registrar_resultado` (`presentada → pagada | con_debitos`, guarda reconocidos, motivos, `total_reconocido` y `resuelta_por`/`resuelta_at`), validando el grafo de D4 y la coherencia entre `resultado` y los montos.
  - Verificar con `tests/test_liquidaciones_estados.py`: cierre exitoso; borrador vacío → `422`; resultado con recortes → `con_debitos`; resultado con total reconocido → `pagada`; `resultado = pagada` con montos reconocidos menores → `422`; transición inválida (p. ej. `borrador → pagada`) → `409`; eventos de auditoría de presentación y resultado.

- [x] 3.4 **Anulación por baja lógica y liberación del turno** (TDD)
  - Implementar `anular_liquidacion` (`borrador → anulada` con motivo obligatorio, `vigente = false` en todo el detalle, auditoría con `antes`/`despues`) y el flip de `vigente` a `false` al pasar a `pagada`.
  - Verificar con `tests/test_liquidaciones_estados.py`: anular borrador conserva cabecera y detalle, deja `anulada_motivo` y habilita re-liquidar el turno; `409` al anular `presentada`/`pagada`/`con_debitos`; `pagada` pone `vigente = false` en todos los detalles; no se ejecuta ningún `DELETE` físico (el detalle sigue existiendo).

- [x] 3.5 **Constraint de doble liquidación del mismo turno (`RN-OS-02`)** (TDD)
  - Verificar la garantía en las dos capas: rechazo `409` en el caso de uso y violación de `uq_liquidacion_detalle_turno_abierto` al insertar el detalle por segunda vez vía ORM.
  - Verificar con `tests/test_liquidaciones_unicidad.py`: dos borradores de la misma OS/período → `409` en el segundo; mismo turno en liquidaciones de OS distintas → permitido; mismo turno en períodos distintos → permitido; tras anular, el mismo turno entra en una nueva liquidación; inserción directa duplicada lanza `IntegrityError`.

## 4. API, RBAC y exportación

- [x] 4.1 **Router `/api/liquidaciones` completo, matriz RBAC y registro en `main.py`** (TDD)
  - Crear `src/backend/app/api/routers/liquidaciones.py` con `POST/GET/GET {id}/PATCH`, `POST /{id}/cerrar`, `POST /{id}/resultado`, `DELETE /{id}` (body `{motivo}`) y `GET /{id}/exportar`, tomando `tenant_id` y actores del JWT (`R4`). Ajustar `MATRIZ[Recurso.LIQUIDACIONES]` a `Dueño: CRUD + EXPORTAR`, `Recepción: CRUD + EXPORTAR`, `Odontólogo: SOLO_LECTURA` (D8) y montar el router en `main.py` y en `tests/conftest.py`.
  - Verificar con `tests/test_liquidaciones_api.py`: ciclo completo `POST → PATCH → /cerrar → /resultado → DELETE` sobre otro borrador; `403` para Odontólogo en crear/editar/presentar/anular/exportar y `200` en `GET`; `404` para liquidaciones de otro tenant; `409` por doble borrador; `422` por período inválido; respuesta con `detalles` y `arancel_vencido` por fila.
  - Actualizar `tests/test_rbac_matriz.py` con los permisos nuevos de exportación sobre `LIQUIDACIONES`.

- [x] 4.2 **Exportación CSV y JSON generada en servidor (`RN-OS-03`, `R8`, `R9`)** (TDD)
  - Implementar `exportar_liquidacion` (D7): CSV UTF-8 con BOM, separador `,`, decimal `.`, quoting RFC 4180 y una fila por turno con montos y `debito_motivo`; JSON con cabecera + detalle y `Decimal` como string. `Content-Disposition: attachment; filename="liquidacion-{os}-{periodo}.{ext}"`.
  - Verificar con `tests/test_liquidaciones_export.py`: CSV de una liquidación `con_debitos` incluye el `debito_motivo` y no incluye DNI/teléfono del paciente; JSON incluye cabecera y las tres filas; `formato=xml` → `422`; `403` para Odontólogo; el contenido no depende de parámetros de monto enviados por el cliente.

## 5. Integración, calidad y documentación

- [x] 5.1 **Verificación integral del change** (calidad)
  - Ejecutar `pytest` completo (con `DATABASE_URL_TEST` apuntando al Postgres del contenedor, `R11`), `ruff check .` y `mypy src/backend`; confirmar suite previa sin regresiones y cobertura de los nuevos módulos.
  - Verificar además que `openspec validate c-13-obras-sociales-liquidacion --strict` siga en verde.
  - Resultado (2026-11-04): **508 passed, 4 skipped, 1 failed en 188,03 s**. El único fallo es preexistente y ajeno al change (`tests/test_catalogo_documentacion.py::test_rutas_catalogo_existen_en_la_app`: falta `GET /api/admin/sillones`, deuda de `C-04`); los 4 skips son Postgres-only (`dialecto`). Sin Docker disponible, la suite corre contra SQLite file de `tests/conftest.py`, que expone `dialecto` para saltear los casos que requieren Postgres.
  - `openspec validate c-13-obras-sociales-liquidacion --strict`: **válido**. `mypy src/backend/app src/backend/alembic`: **1 error preexistente** (`jose` sin stubs en `infrastructure/security/jwt.py`). `ruff check`/`ruff format --check`: 13 errores y 3 archivos sin formatear, todos deuda preexistente de `C-12`/`C-04` (se normalizaron sólo los archivos del change: `012_obras_sociales_liquidacion.py`, `application/cobertura.py`, `test_os_cobertura_api.py`, `test_liquidacion_os_dominio.py`).
  - Cobertura conceptual: los 34 escenarios de la spec tienen test; se agregó `tests/test_liquidaciones_negocio.py::test_borrador_registra_auditoria_del_alta_sin_phi` para el alta auditada que exigía el requisito de auditoría.

- [x] 5.2 **Documentación del change y corrección de `CHANGES.md`**
  - Documentar los endpoints nuevos en `README.md` y en la sección correspondiente de `CHANGES.md`; corregir la línea "Migración 011: tablas `liquidacion_os`, `liquidacion_detalle`" del bloque `[C-13]` para que diga `012_obras_sociales_liquidacion` y refleje los estados reales (`borrador`, `presentada`, `pagada`, `con_debitos`, `anulada`).
  - Verificar que la sección `[C-13]` de `CHANGES.md` y el `README.md` mencionen `/api/os/cobertura`, `/api/liquidaciones`, `/cerrar`, `/resultado`, `/exportar` y que no quede ninguna referencia a la migración `011` como parte de este change.
  - Resultado: `README.md` suma la sección "Obras Sociales y Liquidación (C-13)" con la migración `012`, la cobertura compartida, la tabla de endpoints con RBAC y el formato de export `?formato=csv|json`; el bloque `[C-13]` de `CHANGES.md` pasa a `[x]`, nombra `012_obras_sociales_liquidacion`, los cinco estados reales y los endpoints reales. `Select-String -Path CHANGES.md -Pattern "011"` no devuelve ninguna mención dentro de `[C-13]` (sólo quedan las de `C-12`).

## 6. Bloque E: fixes post-review (code-review de C-13, 2026-11-04)

> Origen: code review de C-13 (2026-11-04) que bloqueó el archivado (2 BLOCKER + 5 SHOULD-FIX + NITs). La fuente de verdad es `docs/reviews/2026-11-04-c-13-fix-plan.md`; las decisiones de diseño que agrega están en `design.md` (D3/D4/D6 ampliadas y D9..D12). Todas las tareas arrancan pendientes: primero el test que falla (RED), después el mínimo código (GREEN), luego los bordes que triangulan.
> Baseline al abrir el bloque: `pytest -q` → 1 failed (preexistente y ajeno: `tests/test_catalogo_documentacion.py::test_rutas_catalogo_existen_en_la_app`, deuda de `C-04`), 508 passed, 4 skipped.

- [x] E.1 **Claim único del turno por obra social y período** (TDD, D9, BLOCKER 1)
  - Implementar la membresía del borrador en `generar_borrador` (`src/backend/app/application/liquidaciones.py`): excluir **todo** turno con detalle en cualquier liquidación de esa obra social y período cuya cabecera no esté `anulada` (incluidas `pagada` y `con_debitos`), no sólo los que están `vigente`. Los turnos excluidos se informan en `advertencias`; si no queda ningún turno nuevo, el alta responde `422` con el mensaje "no hay turnos nuevos para liquidar en ese período". `vigente` conserva su semántica de "liquidación abierta" y deja de ser la señal de "ya reclamado".
  - Verificar con `tests/test_liquidaciones_estados.py`: reescribir `test_tras_pagar_el_alta_avisa_que_es_complementaria` (encodaba el bug) como `test_tras_pagar_el_alta_complementaria_no_reclama_los_turnos_pagados`.
  - Verificar con `tests/test_liquidaciones_unicidad.py`: agregar `test_el_turno_pagado_no_entra_en_una_liquidacion_complementaria`, `test_la_complementaria_sin_turnos_nuevos_da_422` y `test_la_anulacion_libera_el_reclamo_del_turno` (deja el turno reclamable de nuevo).
  - Verificar con `tests/test_liquidaciones_negocio.py`: agregar `test_el_borrador_informa_los_turnos_ya_reclamados_en_las_advertencias`.
  - Verificar con: `pytest -q tests/test_liquidaciones_unicidad.py tests/test_liquidaciones_estados.py tests/test_liquidaciones_negocio.py`
  - Resultado (2026-11-04): Claim único implementado: `generar_borrador` excluye todo turno con detalle en cualquier liquidación de esa OS/período **no anulada** (incluidas `pagada` y `con_debitos`), los excluidos se informan en `advertencias` y, si no queda ninguno, el alta responde `422`. `vigente` conserva su semántica de "liquidación abierta". 3 tests nuevos + 1 reescrito (`test_tras_pagar_el_alta_complementaria_no_reclama_los_turnos_pagados`, que encodaba el bug). Verde en SQLite y Postgres.

- [x] E.2 **El resultado no puede repetir un turno y el total sale del detalle persistido** (TDD, D10, BLOCKER 2)
  - Implementar `model_validator(mode="after")` en `ResultadoOSInput` y `LiquidacionOSDebitosInput` (`src/backend/app/api/schemas_liquidaciones.py`) que rechace `turno_id` repetidos (`422` en el borde) y repetir la misma comprobación en `registrar_resultado` (defensa en profundidad). El `total_reconocido` se recalcula con `_recalcular_totales` sobre el **detalle persistido**, nunca sumando el payload.
  - Verificar con `tests/test_schemas_liquidaciones.py`: agregar `test_el_resultado_rechaza_turnos_repetidos` y `test_los_debitos_rechazan_turnos_repetidos`.
  - Verificar con `tests/test_liquidaciones_estados.py`: agregar `test_el_resultado_con_turno_repetido_da_422` y `test_el_total_reconocido_se_recalcula_desde_el_detalle_persistido`.
  - Verificar con `tests/test_liquidaciones_negocio.py`: agregar `test_el_total_reconocido_no_depende_del_payload`.
  - Verificar con: `pytest -q tests/test_schemas_liquidaciones.py tests/test_liquidaciones_estados.py tests/test_liquidaciones_negocio.py`
  - Resultado (2026-11-04): `model_validator(mode="after")` en `ResultadoOSInput` y `LiquidacionOSDebitosInput` (422 en el borde) + defensa en profundidad en `registrar_resultado`; el `total_reconocido` se recalcula con `_recalcular_totales` sobre el detalle persistido (nunca desde el payload). 4 tests nuevos. Verde en SQLite y Postgres.

- [x] E.3 **`IntegrityError` por carrera devuelve `409` y no `500`** (TDD, D11, SHOULD-FIX a)
  - Implementar en `generar_borrador` el alta del borrador y su detalle dentro de `session.begin_nested()` (SAVEPOINT) y traducir el `IntegrityError` a `Conflicto` (`409`) con el patrón de `src/backend/app/api/routers/admin_catalogo.py`. **No** usar `session.rollback()` (aborta la transacción del request).
  - Verificar con `tests/test_liquidaciones_unicidad.py`: agregar `test_la_carrera_de_dos_altas_devuelve_409_y_un_solo_borrador`.
  - Verificar con `tests/test_liquidaciones_api.py`: agregar `test_alta_concurrente_devuelve_409_y_no_500`.
  - Verificar con: `pytest -q tests/test_liquidaciones_unicidad.py tests/test_liquidaciones_api.py`
  - Resultado (2026-11-04): Alta de cabecera y detalle dentro de `session.begin_nested()` (SAVEPOINT) y traducción del `IntegrityError` a `Conflicto` (409), sin `session.rollback()`. 2 tests: carrera real contra el índice (Postgres) e `IntegrityError` inyectada en la API (nunca 500). Verde.

- [x] E.4 **Lock pesimista de cabecera para que la inmutabilidad valga bajo concurrencia** (TDD, D11, SHOULD-FIX b)
  - Implementar `obtener_liquidacion(..., bloquear=True)` con `with_for_update()` (Postgres lo aplica, SQLite lo ignora) y usarlo en `registrar_debitos`, `presentar_liquidacion`, `registrar_resultado` y `anular_liquidacion`: las mutaciones de una misma liquidación se serializan y el detalle presentado queda efectivamente inmutable. La variante con columna `version` queda como follow-up.
  - Verificar con `tests/test_liquidaciones_estados.py`: agregar `test_la_edicion_concurrente_de_una_presentada_da_409_y_no_muta_el_detalle`.
  - Verificar con `tests/test_liquidaciones_negocio.py`: agregar `test_la_edicion_concurrente_del_borrador_no_pisa_el_detalle`.
  - Verificar con: `pytest -q tests/test_liquidaciones_estados.py tests/test_liquidaciones_negocio.py`
  - Resultado (2026-11-04): `obtener_liquidacion(..., bloquear=True)` con `with_for_update()` **más** comparación de la foto cruda del detalle antes/después del lock: con sólo el lock la perdedora leía el estado ya actualizado y pisaba los montos; ahora recibe `409` sin mutar el detalle. 2 tests (Postgres). Verde.

- [x] E.5 **`con_debitos → pagada` conserva el saldo reconocido y el débito** (TDD, D4 ampliada, SHOULD-FIX c)
  - Implementar la coherencia **por transición** en `registrar_resultado`: `presentada → pagada` exige `total_reconocido == total`; `presentada → con_debitos` exige `total_reconocido < total`; `con_debitos → pagada` exige que el reconocido nuevo sea `>=` al previamente reconocido y **conserva** el `debito_motivo` ya cargado. Agregar el campo derivado `saldo_debito = total - total_reconocido` en `LiquidacionOSRead` y en la exportación.
  - Verificar con `tests/test_liquidaciones_estados.py`: agregar `test_la_con_debitos_pasa_a_pagada_conservando_el_saldo_reconocido` y `test_la_con_debitos_pasa_a_pagada_con_un_reconocido_menor_da_422`.
  - Verificar con `tests/test_schemas_liquidaciones.py`: agregar `test_lectura_expone_el_saldo_debito`.
  - Verificar con `tests/test_liquidaciones_export.py`: agregar `test_el_csv_de_una_pagada_con_debitos_incluye_el_saldo_debito`.
  - Verificar con: `pytest -q tests/test_liquidaciones_estados.py tests/test_schemas_liquidaciones.py tests/test_liquidaciones_export.py`
  - Resultado (2026-11-04): Coherencia por transición en `registrar_resultado` (`presentada→pagada` exige el total, `presentada→con_debitos` exige menos, `con_debitos→pagada` exige no reconocer menos y conserva el `debito_motivo`). `saldo_debito` como `@computed_field` derivado (`None` mientras no hay resultado) en la lectura, el JSON y el CSV (última columna). 5 tests. Verde.

- [x] E.6 **Completitud del resultado (todo-o-nada) documentada y `422` más útil** (TDD, D10, SHOULD-FIX d)
  - Implementar el mensaje del `422` de resultado incompleto: indicar cuántos turnos faltan y cuáles (`turno_id`, sin PHI) en lugar del mensaje genérico. La completitud todo-o-nada ya quedó documentada en la spec de este change (requisito "Registro del resultado informado por la obra social").
  - Verificar con `tests/test_liquidaciones_estados.py`: agregar `test_el_resultado_incompleto_da_422_informando_cuantos_turnos_faltan` y `test_el_resultado_con_turnos_de_mas_da_422`.
  - Verificar con `tests/test_liquidaciones_api.py`: agregar `test_el_resultado_incompleto_responde_422_con_el_detalle_del_faltante`.
  - Verificar con: `pytest -q tests/test_liquidaciones_estados.py tests/test_liquidaciones_api.py`
  - Resultado (2026-11-04): El `422` de resultado incompleto informa cuántos turnos faltan y cuáles (sólo `turno_id`, sin PHI) y los turnos de más tienen su propio `422`. 3 tests. Verde.

- [x] E.7 **Migración correctiva `013_liquidacion_claim_unico`** (TDD, D12, SHOULD-FIX e)
  - Implementar `src/backend/alembic/versions/013_liquidacion_claim_unico.py` (`revision="013_liquidacion_claim_unico"`, `down_revision="012_obras_sociales_liquidacion"`, reversible): columna `liquidacion_detalle.reclamado BOOLEAN NOT NULL DEFAULT true` con backfill portable en Python vía `op.get_bind()` (a `false` los reclamos de liquidaciones `anulada` y los duplicados preexistentes del mismo `tenant_id`/`turno_id`/`lower(obra_social)`/`periodo` en liquidaciones no anuladas, conservando el más antiguo por `(created_at, id)` y registrando el conteo en el log), columna `liquidacion_os.turnos_sin_cobertura INTEGER NOT NULL DEFAULT 0`, `DROP INDEX uq_liquidacion_detalle_turno_abierto` → `CREATE UNIQUE INDEX uq_liquidacion_detalle_turno_reclamado ON liquidacion_detalle (tenant_id, turno_id, lower(obra_social), periodo) WHERE reclamado` y `DROP INDEX uq_liquidacion_os_borrador` → recreación con `lower(obra_social)`. `downgrade()` revierte índices y dropea las dos columnas. **NO tocar `012_obras_sociales_liquidacion.py`** (ya aplicada) y actualizar el metadata del ORM en `src/backend/app/domain/liquidacion_os.py`.
  - Verificar con `tests/test_migracion_013_liquidacion_claim_unico.py` (archivo nuevo): agregar `test_la_migracion_013_agrega_reclamado_y_turnos_sin_cobertura`, `test_el_indice_reclamado_rechaza_el_segundo_reclamo`, `test_el_backfill_libera_los_reclamos_anulados_y_duplicados` y `test_la_migracion_013_es_reversible`.
  - Verificar con `tests/test_migracion_012_obras_sociales_liquidacion.py`: los tests de la `012` siguen verdes sin modificaciones (la `012` queda intacta).
  - Verificar con: `pytest -q tests/test_migracion_013_liquidacion_claim_unico.py tests/test_migracion_012_obras_sociales_liquidacion.py`
  - Resultado (2026-11-04): Migración correctiva `013_liquidacion_claim_unico` (reversible, encadenada sobre la `012`, que queda intacta) + metadata del ORM alineado con Alembic (`create_all` genera el mismo DDL): columna `reclamado`, columna `turnos_sin_cobertura` e índices con `lower(obra_social)`. Backfill portable que libera los reclamos de liquidaciones `anulada` y los duplicados preexistentes (conserva el más antiguo por `(created_at, id)`) y deja el conteo en el log. 4 tests nuevos; `alembic upgrade head` aplicado en el Postgres de verificación y round-trip `head → 012 → head` probado. Verde.

- [x] E.8 **Contrato del `POST /api/liquidaciones` corregido en el design** (D1, D2, SHOULD-FIX f)
  - Implementar la corrección de contrato: la cobertura del borrador se resuelve por el **día de atención de cada turno**, así que el alta no lleva `fecha_referencia`; el lookup con fecha vive en `GET /api/os/cobertura?fecha=...`. El `design.md` ya quedó corregido en esta pasada de documentación; falta blindarlo con un test de contrato.
  - Verificar con `tests/test_liquidaciones_api.py`: agregar `test_el_alta_rechaza_fecha_referencia_con_422`.
  - Verificar con `tests/test_os_cobertura_api.py`: los tests del lookup por `fecha` y por `turno_id` siguen verdes sin modificaciones.
  - Verificar con: `pytest -q tests/test_liquidaciones_api.py tests/test_os_cobertura_api.py`
  - Resultado (2026-11-04): Test de contrato: el `POST` rechaza `fecha_referencia` con `422` (`extra='forbid'`) y el lookup `GET /api/os/cobertura?fecha=` sigue verde. 1 test. Verde.

- [x] E.9 **Persistencia real: `commit` en el router y `turnos_sin_cobertura` en la cabecera** (TDD, D12, N8, SHOULD-FIX g)
  - Implementar en `src/backend/app/api/routers/liquidaciones.py` el cierre explícito de la transacción (`await session.commit()`) al terminar cada mutación: hoy el router nunca confirma y en producción no se persiste (deuda preexistente también en `pacientes`, `presupuestos`, `caja` y `clinica`: follow-up aparte, se corrige sólo en C-13). Persistir `turnos_sin_cobertura` en `liquidacion_os` y leerlo en `_armar_read`, para que el valor sea el mismo en el alta y en las lecturas.
  - Verificar con `tests/test_liquidaciones_api.py`: agregar `test_el_alta_persiste_los_turnos_sin_cobertura_al_releer` y `test_el_alta_confirma_la_transaccion`.
  - Verificar con `tests/test_liquidaciones_negocio.py`: agregar `test_el_alta_persiste_la_cabecera_con_turnos_sin_cobertura`.
  - Verificar con: `pytest -q tests/test_liquidaciones_api.py tests/test_liquidaciones_negocio.py`
  - Resultado (2026-11-04): `await session.commit()` explícito al cerrar cada mutación del router (verificado con una sesión nueva) + `turnos_sin_cobertura` persistido en la cabecera y releído igual que el total (gracias a la columna de E.7). 3 tests (2 de ellos dependían de E.7 y pasaron al aterrizar la `013`). Verde.

- [x] E.10 **Calidad: sin N+1 en el listado, `_monto` unificado y nombre de archivo ASCII + `filename*`** (TDD, N1, N2, N3)
  - Implementar en `listar_liquidaciones` la carga del lote (detalles, turnos y prestaciones) en 3 queries en lugar de una por liquidación; extraer el helper de montos duplicado (`application/liquidaciones.py`, `domain/cobertura_os.py`, `application/caja.py`) a `src/backend/app/shared/montos.py` (`CERO`, `CENTAVOS`, `monto_2dp`); hacer que `_slug_archivo` devuelva sólo ASCII y sumar `filename*=UTF-8''...` (RFC 5987) al `Content-Disposition`, conservando el nombre legible.
  - Verificar con `tests/test_liquidaciones_negocio.py`: agregar `test_el_listado_no_hace_n_plus_1`.
  - Verificar con `tests/test_liquidaciones_export.py`: agregar `test_el_nombre_de_archivo_es_ascii_y_lleva_filename_rfc_5987` y modificar `test_nombre_de_archivo_normaliza_la_obra_social` para exigir el `filename` ASCII y el `filename*` percent-encoded.
  - Verificar con: `pytest -q tests/test_liquidaciones_negocio.py tests/test_liquidaciones_export.py`
  - Resultado (2026-11-04): Listado con **3 queries constantes** (antes 3 por liquidación: 10 SELECTs con 3 liquidaciones, ahora 4) con `_armar_read_desde_datos`; helper de montos unificado en `src/backend/app/shared/montos.py` (`monto_2dp`, `CERO`, `CENTAVOS`) y fuera el `_monto` duplicado de `liquidaciones`, `cobertura_os`, `caja` y `mercadopago`; header de descarga con `filename` ASCII + `filename*=UTF-8''` (RFC 5987), que ya no rompe con obras sociales con acentos. 4 tests nuevos. Verde.

- [x] E.11 **Guard de PHI en textos libres y `observaciones` auditadas** (TDD, N4, `R9`)
  - Implementar un guard que rechace (`422`) DNI o teléfono en los textos libres (`debito_motivo`, `observaciones` y `motivo` de anulación) y agregar `observaciones` al snapshot de `_snapshot_liquidacion` para que quede en la auditoría (append-only, sin identificadores de paciente).
  - Verificar con `tests/test_liquidaciones_negocio.py`: agregar `test_el_debito_con_dni_en_el_motivo_da_422`, `test_las_observaciones_con_telefono_da_422` y `test_las_observaciones_quedan_auditadas`.
  - Verificar con: `pytest -q tests/test_liquidaciones_negocio.py`
  - Resultado (2026-11-04): Guard de PHI en la capa de aplicación (`src/backend/app/domain/textos_libres.py`): rechaza con `422` los `debito_motivo`, `observaciones` y `motivo` que parecen un DNI (7-8 dígitos) o un teléfono (`+` y 10-13 dígitos) sin repetir el dato en el mensaje, y no deja caer los motivos legítimos del negocio; `observaciones` agregado al snapshot de auditoría. 3 tests. Verde.

- [x] E.12 **Bordes de período, KB 03/04, `README.md`, `CHANGES.md` y conteo de escenarios** (TDD, N5, N6, N7)
  - Implementar los bordes del período en los casos de uso (turno iniciado exactamente a las `00:00` del primer día entra; el que arranca a las `00:00` del primer día del período siguiente ya es del período siguiente; el rango es UTC semiabierto) y actualizar la documentación: `knowledge-base/03_actores_y_roles.md` (fila "Liquidaciones OS": Dueño y Recepción con CRUD + exportar) y `knowledge-base/04_modelo_de_datos.md` (los cinco estados incluyendo `anulada`, columnas `reclamado` y `turnos_sin_cobertura`, índices parciales con `lower(obra_social)` y el reclamo único por OS/período); `README.md` y `CHANGES.md` (migración `013`, reclamo único, `saldo_debito`, `con_debitos → pagada`); y el conteo de escenarios de `tasks.md` (de "los 18 escenarios" a los reales).
  - Verificar con `tests/test_liquidaciones_negocio.py`: agregar `test_el_turno_del_primer_dia_del_periodo_entra_al_borrador` y `test_el_turno_del_inicio_del_periodo_siguiente_queda_fuera`.
  - Verificar con `tests/test_liquidacion_os_dominio.py`: agregar `test_el_rango_de_periodo_es_sem_abierto`.
  - Verificar con `tests/test_liquidaciones_documentacion.py` (archivo nuevo): agregar `test_la_kb_documenta_los_cinco_estados_y_el_reclamo_unico`, `test_la_kb_documenta_la_exportacion_de_liquidaciones` y `test_readme_y_changes_documentan_la_migracion_013`.
  - Verificar con: `pytest -q tests/test_liquidaciones_negocio.py tests/test_liquidacion_os_dominio.py tests/test_liquidaciones_documentacion.py`
  - Resultado (2026-11-04): Bordes de período cubiertos con 3 tests (rango UTC semiabierto: entra el que arranca a las `00:00` del primer día, el del período siguiente no) + `tests/test_liquidaciones_documentacion.py` (KB, README y CHANGES) + `knowledge-base/03_actores_y_roles.md` y `knowledge-base/04_modelo_datos.md` actualizados (cinco estados, índices con `lower(obra_social)`, reclamo único, `saldo_debito` derivado) + README y CHANGES con la `013` y las reglas de dinero + conteo de escenarios corregido (34). Verde.

- [x] E.13 **Verificación integral del Bloque E** (calidad)
  - Ejecutar la suite completa contra el Postgres real del entorno de verificación local (17, `127.0.0.1:5433`, con `DATABASE_URL_TEST` / `APP_ROLE_URL_TEST` / `DATABASE_URL_OWNER` del plan de fixes), `ruff check .` y `ruff format --check` sin errores nuevos en los archivos del change, `mypy --config-file src/backend/pyproject.toml src/backend/app src/backend/alembic` sin errores nuevos en los módulos de C-13, y `openspec validate c-13-obras-sociales-liquidacion --strict` en verde.
  - Verificar con: `pytest -q` (con `DATABASE_URL_TEST` apuntando al Postgres del contenedor, `R11`)
  - Verificar con: `ruff check . && ruff format --check .`
  - Verificar con: `mypy --config-file src/backend/pyproject.toml src/backend/app src/backend/alembic`
  - Verificar con: `openspec validate c-13-obras-sociales-liquidacion --strict`
  - Resultado (2026-11-04): Suite completa en SQLite: **549 passed, 7 skipped, 1 failed** (el único fallo es el preexistente y ajeno de `C-04`: `tests/test_catalogo_documentacion.py::test_rutas_catalogo_existen_en_la_app`). C-13 contra **Postgres 17 real** (`127.0.0.1:5433`, base migrada a head): **145 passed, 0 skipped**. `ruff check`: All checks passed; `ruff format --check`: 188 archivos ya formateados; `mypy --config-file src/backend/pyproject.toml`: Success (109 archivos); `openspec validate --strict`: válido. La suite completa contra Postgres conserva **38 failed + 37 errors preexistentes** fuera de C-13 (`caja`, `presupuestos`, `migracion_006`): los seeds mezclan padres e hijos en un mismo `flush` y el ORM no declara `relationship()`, así que Postgres viola la FK (mismo defecto que el fix de seeds de C-13 resolvió en sus archivos). **0 fallos nuevos**.

## Workflow follow-up

- Revisar con `code-review` (governance `MEDIO`) antes de archivar.
- Implementar y dejar en verde el Bloque E (`E.1`..`E.13`) antes de archivar: el archivado queda bloqueado hasta que la verificación integral (E.13) dé 0 fallos nuevos y los 34 escenarios de la spec tengan su test.
- Archivar el change con `/opsx:archive c-13-obras-sociales-liquidacion` una vez verificada la suite completa.
- Push a GitHub al cerrar el change (`R12`).
