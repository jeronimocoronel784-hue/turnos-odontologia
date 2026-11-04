# Design: `c-13-obras-sociales-liquidacion`

## Context
Ver motivación en `proposal.md` y requisitos en `specs/obras-sociales-liquidacion/spec.md`. El estado actual relevante:

- `CoberturaOS` (`src/backend/app/domain/cobertura_os.py`) ya existe con `arancel`, `copago` y vigencia; su CRUD vive en `GET/POST/PATCH/DELETE /api/admin/coberturas` (`src/backend/app/api/routers/admin_catalogo.py`).
- `C-10` calcula la cobertura dentro de `calcular_montos_item_presupuesto` (`src/backend/app/application/presupuestos.py`), con `cobertura_unit = min(precio_particular, arancel)` y `a_cargo = subtotal - cobertura`. **No expone el estado de vigencia del arancel.**
- `C-11` reutiliza esa función desde `calcular_liquidacion_turno` (`src/backend/app/application/caja.py`) para el saldo `precio - cobertura - seña`.
- `Turno` tiene el grafo cerrado de `RN-AG-07` y `finalizado` es terminal (`TRANSICIONES_PERMITIDAS[FINALIZADO] == frozenset()`).
- `Auditoria` es append-only y `registrar_auditoria` (`src/backend/app/application/auditoria.py`) es el único punto de escritura.
- Migración más reciente: `011_mercadopago_webhooks`; por lo tanto `C-13` usa `012_obras_sociales_liquidacion`.

## UI Mockups
Decision: no (no UI — este change entrega modelos, migración, casos de uso, endpoints y exportación; las pantallas de liquidación corresponden a `C-17`).

## Goals / Non-Goals

**Goals:**
- Un único resolvedor de cobertura reutilizado por presupuestos, caja y liquidación, con estado de arancel explícito.
- Lookup de cobertura para agenda/cobro sin duplicar el CRUD de `CoberturaOS`.
- Modelo de liquidación por OS/período con detalle por turno, débitos y constraint de unicidad a nivel base de datos.
- Exportación CSV/JSON generada en servidor.

**Non-Goals:**
- Presentación electrónica, integración con portales de obras sociales o padrón de afiliados (`RN-OS-03`, v2).
- Generar movimientos de caja a partir del pago de una OS (el cobro de la OS se registra por fuera; ver Supuestos).
- Edición manual de la membresía de turnos de una liquidación (el conjunto se deriva del período).
- Frontend.

## Decisions

### D1. Extraer la resolución de cobertura a un servicio compartido (no duplicar `C-10`)
- **Decisión**: separar en dos piezas:
  - `src/backend/app/domain/cobertura_os.py` → función **pura** `resolver_cobertura_desde_candidatas(*, precio_particular, candidatas, fecha_referencia, obra_social) -> ResolucionCobertura` y el enum `EstadoArancel` (`vigente`, `vencido`, `sin_cobertura`).
  - `src/backend/app/application/cobertura.py` → loaders async (`resolver_cobertura_prestacion` para una prestación y `resolver_coberturas_lote` para un conjunto de prestaciones) que consultan `CoberturaOS` y delegan en la función pura.
- **Reutilización**: `calcular_montos_item_presupuesto` (`C-10`) y `calcular_liquidacion_turno` (`C-11`) **no se reescriben**: pasan a ser adaptadores finos que delegan en `resolver_cobertura_prestacion` y conservan exactamente su firma y su retorno (`(precio_unit, cobertura_total, a_cargo_total)` y `LiquidacionTurnoRead`). Los tests existentes `tests/test_presupuestos_negocio.py` y `tests/test_caja_negocio.py` deben seguir verdes sin cambios, como prueba de no-regresión.
- **Razón**: `RN-OS-01` debe tener una sola fuente de verdad; duplicar el cálculo en liquidaciones haría que presupuesto, cobro y liquidación pudieran divergir. La función pura permite TDD sin DB para la matriz de casos (vigente / vencido / sin cobertura / futura).
- **Alternativas descartadas**: (a) copiar el cálculo en `application/liquidaciones.py` — descartado por divergencia garantizada a mediano plazo; (b) mover todo a un "servicio de facturación" nuevo — descartado por sobre-ingeniería para un MVP con governance MEDIO; (c) resolver la cobertura en SQL con una vista — descartado porque el fallback a "arancel vencido más reciente" y el mensaje de advertencia son lógica de dominio que se testea mejor en Python.

### D2. Regla explícita del arancel vencido (`RN-OS-01`, Flujo 5)
- **Decisión**: orden de resolución, con `fecha_referencia` = fecha del turno (o la indicada en el lookup):
  1. Convenio `activa = true`, misma `obra_social` (comparada con `lower()` como en `C-10`) y `prestacion_id`, con `vigencia_desde <= fecha` y (`vigencia_hasta IS NULL` o `>= fecha`) → **`vigente`**.
  2. Si no hay convenio vigente pero sí histórico con `vigencia_desde <= fecha` → **`vencido`**: se usa el de mayor `vigencia_desde` (el último arancel cargado) y se devuelve `advertencia` en rioplatense con la fecha de vencimiento y el arancel usado.
  3. Sin convenio previo, o con `vigencia_desde > fecha` (cobertura futura) → **`sin_cobertura`** (particular, con advertencia en el caso futuro).
- **Razón**: el KB pide "alerta y usa el vigente con aviso"; facturar como particular en silencio le traslada al paciente un costo que la OS sí cubre.
- **Alternativas descartadas**: bloquear la creación de la liquidación ante arancel vencido — descartado porque impide liquidar períodos históricos y el Flujo 5 pide alertar, no bloquear.
- **Invariante**: la marca `arancel_vencido` se **congela en el detalle** al generar el borrador, para que la advertencia no desaparezca si después se carga un arancel nuevo.

### D3. Constraint de unicidad del turno liquidado con índice parcial (`RN-OS-02`)
- **Decisión**: `liquidacion_detalle` desnormaliza `obra_social` y `periodo` (copiados de la cabecera) y agrega el flag `vigente`; el constraint es un **índice único parcial** `uq_liquidacion_detalle_turno_abierto (tenant_id, turno_id, obra_social, periodo) WHERE vigente`.
- **Razón**: `RN-OS-02` habla de "una sola liquidación **abierta**": tras anular o pagar, el turno debe poder re-liquidarse (caso real: la OS devuelve la liquidación y se rehace). Un `UNIQUE` total lo impediría para siempre; un chequeo sólo en aplicación no cumple el principio "la app valida la UX, la DB garantiza" del registry Postgres.
- **Trade-off**: `vigente` es estado derivado; lo mantiene el servicio dentro de la misma transacción al pasar a `pagada`/`anulada` (los estados `presentada` y `con_debitos` siguen abiertos). Se cubre con test dedicado.
- **Alternativas descartadas**: (a) `UNIQUE (turno_id, obra_social, periodo)` total — descartado por lo anterior; (b) constraint diferido/trigger — descartado por portabilidad SQLite/Postgres del proyecto.
- **Enmienda (2026-11-04, code review)**: este índice parcial garantiza la unicidad entre liquidaciones **abiertas**, no la unicidad del **reclamo**. Al pasar a `pagada` el detalle se marca `vigente = false`, así que el mismo turno podía volver a entrar en otra liquidación de la misma OS/período y reclamar dos veces lo ya cobrado. `vigente` conserva su semántica de "liquidación abierta" y deja de ser la señal de "ya reclamado"; la garantía de reclamo único pasa a la columna `reclamado` con su índice parcial (D9, D12). El índice `uq_liquidacion_detalle_turno_abierto` se reemplaza por `uq_liquidacion_detalle_turno_reclamado` en la migración correctiva `013`.

### D4. Modelo de estados con `anulada` para cumplir `R7`
- **Decisión**: `EstadoLiquidacionOS = borrador | presentada | pagada | con_debitos | anulada`, con grafo:
  - `borrador → presentada | anulada`
  - `presentada → pagada | con_debitos`
  - `con_debitos → pagada` (la OS termina pagando el saldo reconocido)
  - `pagada` y `anulada` terminales.
- **Razón**: el KB enumera 4 estados y `DELETE` es parte del "CRUD" pedido, pero `R7` prohíbe hard delete en dominios de dinero. `anulada` es una baja lógica que conserva cabecera y detalle y libera los turnos (`vigente = false`).
- **Alternativas descartadas**: (a) borrado físico del borrador — viola `R7`; (b) columna `deleted_at` sin estado — rompe el grafo explícito que el resto del proyecto usa (`Sena`, `Presupuesto`, `Turno`).
- **Enmienda (2026-11-04, code review)**: la transición `con_debitos → pagada` significa que **la OS pagó el saldo reconocido**, no que respaldó el total reclamado: una liquidación `pagada` puede arrastrar débito (`total_reconocido < total`) y conservar los `debito_motivo` del detalle. La coherencia se valida **por transición**: `presentada → pagada` exige `total_reconocido == total`; `presentada → con_debitos` exige `total_reconocido < total`; `con_debitos → pagada` exige que el reconocido nuevo no sea menor al previamente reconocido. El saldo pendiente se expone como campo derivado `saldo_debito = total - total_reconocido` en la lectura y en la exportación.

### D5. Membresía de turnos derivada del período, inmutable
- **Decisión**: el borrador se arma una sola vez con los turnos `finalizado` cuyo `inicio` cae en `[primer día del período, primer día del período siguiente)` en UTC y cuya prestación tiene convenio con la OS. No se agregan ni quitan turnos manualmente; para corregir se anula el borrador y se regenera.
- **Razón**: `finalizado` es estado terminal en el grafo de turnos, así que la membresía no puede invalidarse después. Editar la membresía manualmente abriría la puerta a liquidar turnos no finalizados por la puerta de atrás.
- **Alternativas descartadas**: `POST /{id}/detalles` — descartado por scope creep y por romper la derivación determinística período→turnos.

### D6. Liquidaciones complementarias por período (período ya cerrado)
- **Decisión**: se permite más de una liquidación por OS/período (p. ej. un turno finalizado tarde o un ajuste tras un pago). Lo único bloqueado es **un segundo `borrador` simultáneo** para la misma OS/período (índice único parcial `uq_liquidacion_os_borrador`). Si el período ya tiene una liquidación `pagada`, el alta devuelve una advertencia "esta liquidación se tratará como complementaria".
- **Razón**: bloquean el caso de negocio real sin renunciar al constraint de `RN-OS-02` (que es por turno, no por período).
- **Alternativas descartadas**: (a) único por OS/período — impide el ajuste; (b) sin límite de borradores — permite crear N borradores duplicados por error.
- **Enmienda (2026-11-04, code review)**: la complementaria queda **acotada a los turnos nunca reclamados** por esa obra social y período: el alta excluye todo turno que ya tenga detalle en una liquidación no anulada (incluidas `pagada` y `con_debitos`) y avisa por `advertencias` cuáles quedaron afuera; si no queda ningún turno nuevo, el alta responde `422` ("no hay turnos nuevos para liquidar en ese período") en lugar de generar una liquidación vacía. El **ajuste de una liquidación ya presentada o pagada queda fuera de alcance en v1**: una liquidación presentada es inmutable y no se anula, así que corregir un reclamo ya presentado no se resuelve con otra liquidación (ver Supuestos).

### D7. Exportación en servidor sin PHI innecesaria (`RN-OS-03`, `R8`, `R9`)
- **Decisión**: `GET /api/liquidaciones/{id}/exportar?formato=csv|json` arma el contenido en backend y lo devuelve con `Content-Disposition`. Columnas: `periodo, obra_social, estado, estado_arancel, turno_id, fecha_turno, prestacion, monto_reclamado, monto_reconocido, debito_motivo`. CSV en UTF-8 con BOM, separador `,` y decimal `.` (RFC 4180).
- **Razón**: `R8` prohíbe cálculo en cliente y `R9` exige mínimo necesario: la OS necesita el turno y el monto, no el DNI ni el teléfono del paciente.
- **Alternativas descartadas**: (a) CSV con separador `;` y coma decimal (locale es-AR) — descartado por interoperabilidad con planillas de OS y parsers; (b) incluir nombre/DNI del paciente — descartado por mínimo necesario (queda como posible extensión si una OS lo exige, y ahí se evalúa con governance HIGH).

### D8. Permiso de exportación explícito en la matriz RBAC
- **Decisión**: `MATRIZ[Recurso.LIQUIDACIONES]` pasa a `dueno: CRUD + EXPORTAR`, `recepcion: CRUD + EXPORTAR`, `odontologo: SOLO_LECTURA`. No se agrega `Accion` nueva: se reutiliza `Accion.EXPORTAR`.
- **Razón**: el odontólogo debe poder leer la cobertura de sus turnos, pero no exportar la liquidación del consultorio (la matriz de §03 le da exportación "parcial (clínica propia)"). La fila "Liquidaciones OS" de §03 dice CRUD para Dueño y Recepción, que son los roles que liquidan.
- **Alternativas descartadas**: (a) exigir además `Recurso.EXPORTACION` — el odontólogo también lo tiene y no filtra nada; (b) rol hardcodeado en el router — duplica la fuente de verdad del RBAC.

### D9. Un turno se reclama una sola vez por obra social y período (mientras la liquidación no esté `anulada`)
- **Decisión**: la membresía del borrador excluye **todo** turno que tenga detalle en cualquier liquidación de esa obra social y período cuya cabecera **no** esté `anulada` (incluye `pagada` y `con_debitos`), no sólo los que están `vigente`. Los turnos excluidos se informan por `advertencias`; si no queda ninguno → `422` ("no hay turnos nuevos para liquidar en ese período"). `vigente` conserva su semántica de "liquidación abierta" y deja de ser la señal de "ya reclamado". La garantía de DB es la columna `liquidacion_detalle.reclamado BOOLEAN` con el índice único parcial `uq_liquidacion_detalle_turno_reclamado (tenant_id, turno_id, lower(obra_social), periodo) WHERE reclamado` (migración correctiva `013`).
- **Razón**: el bug del BLOCKER 1 — al pagar, el detalle quedaba `vigente = false` y una complementaria volvía a reclamar (y a cobrar) turnos ya liquidados. El reclamo es un hecho económico, no un estado de edición: sólo la anulación (baja lógica) libera el turno.
- **Alternativas descartadas**: (a) seguir usando `vigente` como señal de "ya reclamado" — descartado por el bug; (b) anular automáticamente la liquidación `pagada` para liberar el turno — descartado por `R7` y por perder la trazabilidad del cobro; (c) `UNIQUE` total sin `WHERE` — descartado porque bloquearía de por vida el mismo turno en períodos distintos.

### D10. Resultado de la OS: todo-o-nada, total recalculado desde el detalle persistido
- **Decisión**: `model_validator(mode="after")` en `ResultadoOSInput` y `LiquidacionOSDebitosInput` rechaza `turno_id` repetidos (`422` en el borde) y la misma comprobación se repite en `registrar_resultado` (defensa en profundidad). El `total_reconocido` se recalcula con `_recalcular_totales` sobre el **detalle persistido**, nunca desde el payload. La transición `con_debitos → pagada` exige `reconocido_nuevo >= reconocido_previo` (no igualdad con `total`) y **conserva** el `debito_motivo` ya cargado; el saldo pendiente se expone como campo derivado `saldo_debito = total - total_reconocido`.
- **Razón**: el bug del BLOCKER 2 — la comparación por `sets` borraba los `turno_id` duplicados y el total se sumaba desde el payload, con lo cual un payload `[{t1, 20000}, {t1, 20000}, {t2, 0}]` cerraba como `pagada` con cabecera 40000 y detalle 20000. El total tiene que salir de lo que queda escrito en la base, no de lo que dice el cliente (`R8`).
- **Alternativas descartadas**: (a) deduplicar los `turno_id` repetidos y tomar el último — descartado por ser una decisión silenciosa del servidor; (b) aceptar el total del cliente — descartado por `R8`; (c) permitir resultados parciales — descartado porque obligaría a un modelo de liquidación incremental que no está en el alcance de v1.

### D11. Serialización de las mutaciones (`FOR UPDATE`) y traducción de `IntegrityError` → `409`
- **Decisión**: `obtener_liquidacion(..., bloquear=True)` usa `with_for_update()` (Postgres sí, SQLite lo ignora) y lo usan `registrar_debitos`, `presentar_liquidacion`, `registrar_resultado` y `anular_liquidacion`: las mutaciones sobre una misma liquidación se serializan y el detalle de una liquidación presentada queda efectivamente inmutable. La carrera de dos altas simultáneas se resuelve con `session.begin_nested()` (SAVEPOINT) y la traducción del `IntegrityError` a `Conflicto` (`409`), con el patrón de `api/routers/admin_catalogo.py`.
- **Razón**: sin serialización, dos mutaciones concurrentes leen el mismo detalle y la segunda pisa a la primera; y una carrera de altas terminaba en `500` porque el `IntegrityError` del índice único no se traducía.
- **Alternativas descartadas**: (a) `session.rollback()` ante el `IntegrityError` — descartado porque aborta la transacción del request; (b) columna `version` con bloqueo optimista — descartado para este change por ser más invasivo, queda como follow-up; (c) `SELECT ... FOR UPDATE` sobre las filas de detalle — descartado por no alcanzar la cabecera, que es la que define la transición de estado.

### D12. Garantías de DB corregidas: reclamo único, `lower(obra_social)` y `turnos_sin_cobertura` persistido
- **Decisión**: migración correctiva `013_liquidacion_claim_unico` (`down_revision = "012_obras_sociales_liquidacion"`, reversible) que **no toca la `012`** (ya aplicada en bases existentes): agrega `liquidacion_detalle.reclamado BOOLEAN NOT NULL DEFAULT true` con backfill en Python (`op.get_bind()`), agrega `liquidacion_os.turnos_sin_cobertura INTEGER NOT NULL DEFAULT 0`, y reemplaza los dos índices únicos parciales por versiones con la expresión `lower(obra_social)` (`uq_liquidacion_detalle_turno_reclamado` y `uq_liquidacion_os_borrador`). El metadata del ORM (`app/domain/liquidacion_os.py`) se actualiza en el mismo change (los tests usan `Base.metadata.create_all`, no Alembic).
- **Razón**: la app compara la obra social con `lower()`, así que un índice case-sensitive dejaba pasar dos reclamos de la misma OS con distinta capitalización; y `turnos_sin_cobertura` era un valor de respuesta que se perdía al releer la liquidación.
- **Alternativas descartadas**: (a) modificar la `012` — descartado porque ya está aplicada en bases existentes; (b) normalizar `obra_social` a minúsculas en la columna — descartado por perder la forma en que la OS escribe su nombre; (c) índices case-sensitive con `COLLATE` — descartado por no ser portable a SQLite en los tests.

## Modelo de datos final

### Tabla `liquidacion_os`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | GUID (CHAR 32) | PK |
| `tenant_id` | GUID | FK `tenant.id` `ON DELETE CASCADE`, `NOT NULL` |
| `obra_social` | VARCHAR(160) | `NOT NULL`, normalizada con `trim` |
| `periodo` | CHAR(6) | `NOT NULL`, `yyyymm` |
| `estado` | VARCHAR(24) | `NOT NULL`, default `'borrador'` |
| `total` | NUMERIC(12,2) | `NOT NULL`, default `0.00`, suma de `monto_reclamado` |
| `total_reconocido` | NUMERIC(12,2) | `NULL` hasta el resultado de la OS |
| `turnos_sin_cobertura` | INTEGER | `NOT NULL`, default `0`, conteo persistido del alta (D12) |
| `observaciones` | TEXT | `NULL` |
| `presentada_por` / `presentada_at` | GUID FK `usuario` RESTRICT / TIMESTAMPTZ | `NULL` en borrador |
| `resuelta_por` / `resuelta_at` | GUID FK `usuario` RESTRICT / TIMESTAMPTZ | `NULL` hasta `pagada`/`con_debitos` |
| `anulada_motivo` | TEXT | Obligatorio si `estado = 'anulada'` |
| `created_by` | GUID FK `usuario` RESTRICT | `NOT NULL` |
| `created_at` / `updated_at` | TIMESTAMPTZ | `AuditMixin` |

Constraints:
- `ck_liquidacion_os_estado_valido`: `estado IN ('borrador','presentada','pagada','con_debitos','anulada')`.
- `ck_liquidacion_os_periodo_largo`: `length(periodo) = 6` (el formato `yyyymm` se valida además en Pydantic y en dominio, porque Postgres y SQLite no comparten operador de regex).
- `ck_liquidacion_os_totales_no_negativos`: `total >= 0 AND (total_reconocido IS NULL OR total_reconocido >= 0) AND (total_reconocido IS NULL OR total_reconocido <= total)`.
- `ck_liquidacion_os_presentada_completa`: `estado IN ('borrador','anulada') OR (presentada_por IS NOT NULL AND presentada_at IS NOT NULL)`.
- `ck_liquidacion_os_resuelta_completa`: `estado NOT IN ('pagada','con_debitos') OR (total_reconocido IS NOT NULL AND resuelta_por IS NOT NULL AND resuelta_at IS NOT NULL)`.
- `ck_liquidacion_os_anulada_motivo`: `estado <> 'anulada' OR (anulada_motivo IS NOT NULL AND length(trim(anulada_motivo)) > 0)`.

Índices:
- `uq_liquidacion_os_borrador`: `UNIQUE (tenant_id, lower(obra_social), periodo) WHERE estado = 'borrador'` (D6, D12: la expresión `lower()` alinea el índice con la comparación de la app).
- `ix_liquidacion_os_tenant_os_periodo`: `(tenant_id, obra_social, periodo)`.
- `ix_liquidacion_os_tenant_estado`: `(tenant_id, estado)`.

### Tabla `liquidacion_detalle`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | GUID | PK |
| `tenant_id` | GUID | FK `tenant.id` CASCADE |
| `liquidacion_id` | GUID | FK `liquidacion_os.id` **RESTRICT** (nunca borra detalle en cascada, `R7`) |
| `turno_id` | GUID | FK `turno.id` RESTRICT |
| `obra_social` / `periodo` | VARCHAR(160) / CHAR(6) | Copia de la cabecera para el índice parcial (D3) |
| `monto_reclamado` | NUMERIC(12,2) | Calculado en servidor con el arancel resuelto |
| `monto_reconocido` | NUMERIC(12,2) | `NULL` hasta el resultado de la OS |
| `debito_motivo` | TEXT | Obligatorio si hay recorte (D5) |
| `arancel_vencido` | BOOLEAN | Snapshot del estado al generar el borrador (D2) |
| `vigente` | BOOLEAN | `true` mientras la liquidación está abierta (D3); deja de ser la señal de "ya reclamado" (D9) |
| `reclamado` | BOOLEAN | `NOT NULL`, default `true`; el reclamo sigue vigente mientras la liquidación no esté `anulada` (D9, D12) |
| `created_at` / `updated_at` | TIMESTAMPTZ | `AuditMixin` |

Constraints:
- `uq_liquidacion_detalle_turno`: `UNIQUE (liquidacion_id, turno_id)`.
- `uq_liquidacion_detalle_turno_reclamado`: `UNIQUE (tenant_id, turno_id, lower(obra_social), periodo) WHERE reclamado` (D9, D12; reemplaza a `uq_liquidacion_detalle_turno_abierto`, que queda sólo en la `012` y se dropea en la `013`).
- `ck_liquidacion_detalle_montos`: `monto_reclamado >= 0 AND (monto_reconocido IS NULL OR (monto_reconocido >= 0 AND monto_reconocido <= monto_reclamado))`.
- `ck_liquidacion_detalle_debito_motivo`: `monto_reconocido IS NULL OR monto_reconocido = monto_reclamado OR (debito_motivo IS NOT NULL AND length(trim(debito_motivo)) > 0)`.
- `ck_liquidacion_detalle_periodo_largo`: `length(periodo) = 6`.

Índices: `ix_liquidacion_detalle_liquidacion_id`, `ix_liquidacion_detalle_tenant_turno`.

### Módulos
- `src/backend/app/domain/liquidacion_os.py`: enums, grafo (`es_transicion_liquidacion_valida`), helpers de período (`periodo_desde_fecha`, `rango_periodo`, `periodo_valido`) y modelos.
- `src/backend/app/application/liquidaciones.py`: casos de uso.
- `src/backend/app/application/cobertura.py`: loaders de cobertura (D1).
- `src/backend/app/shared/montos.py`: `CERO`, `CENTAVOS` y `monto_2dp` compartidos por liquidaciones, cobertura y caja (evita la copia de `_monto`).
- `src/backend/app/api/schemas_liquidaciones.py` y `src/backend/app/api/routers/liquidaciones.py`.

## Contrato de endpoints

| Método | Ruta | Input | Output / errores |
|---|---|---|---|
| GET | `/api/os/cobertura` | query: `prestacion_id` (req), `obra_social?`, `fecha?`, `turno_id?`, `cantidad` (1..99) | `200 CoberturaLookupRead`; `404` prestación/turno inexistente en el tenant; `422` si `turno_id` y `prestacion_id` se contradicen |
| POST | `/api/liquidaciones` | `{obra_social, periodo}` (la cobertura se resuelve por el día de atención de cada turno, D1/D2: no hay `fecha_referencia`) | `201 LiquidacionOSRead`; `409` si ya hay borrador de esa OS/período o si una alta concurrente choca contra el índice (D11); `422` si no hay turnos finalizados con cobertura o si no hay turnos nuevos para liquidar en ese período (D9) |
| GET | `/api/liquidaciones` | query `obra_social?`, `periodo?`, `estado?` | `200 list[LiquidacionOSRead]` |
| GET | `/api/liquidaciones/{id}` | — | `200 LiquidacionOSRead` con `detalles`; `404` fuera del tenant |
| PATCH | `/api/liquidaciones/{id}` | `{observaciones?, detalles: [{turno_id, monto_reconocido, debito_motivo?}]}` | `200 LiquidacionOSRead`; `409` si no está en `borrador` (o si otra mutación lo dejó inmutable, D11); `422` débito sin motivo o `turno_id` repetido (D10) |
| POST | `/api/liquidaciones/{id}/cerrar` | `{observaciones?}` | `200`; `409` estado inválido; `422` sin turnos |
| POST | `/api/liquidaciones/{id}/resultado` | `{resultado: pagada\|con_debitos, detalles: [{turno_id, monto_reconocido, debito_motivo?}]}` | `200`; `409`/`422` según grafo, coherencia por transición (D4) y duplicados de `turno_id` (D10) |
| DELETE | `/api/liquidaciones/{id}` | body `{motivo}` | `200 LiquidacionOSRead` en `anulada`; `409` si no está en `borrador` |
| GET | `/api/liquidaciones/{id}/exportar` | query `formato=csv\|json` | `200` archivo con `Content-Disposition`; `422` formato inválido |

`CoberturaLookupRead`:
```json
{
  "prestacion_id": "uuid", "obra_social": "OSDE", "cobertura_id": "uuid|null",
  "precio_particular": "50000.00", "cobertura": "30000.00", "monto_a_cargo": "20000.00",
  "estado_arancel": "vigente|vencido|sin_cobertura",
  "vigencia_desde": "2026-01-01|null", "vigencia_hasta": "2026-10-31|null",
  "arancel_vencido": false, "advertencia": "null|texto"
}
```

`LiquidacionOSRead` incluye cabecera + `total`, `total_reconocido`, `saldo_debito` (derivado: `total - total_reconocido`, `null` mientras no hay resultado), `turnos_sin_cobertura` (persistido), `advertencias: [str]` y `detalles: [{turno_id, fecha_turno, prestacion, monto_reclamado, monto_reconocido, debito_motivo, arancel_vencido}]`. Todos los inputs usan `extra='forbid'` (`R1`); `tenant_id` y actores salen del JWT (`R4`); ningún schema de entrada acepta montos de totales (`R8`).

## Matriz RBAC (`Recurso.LIQUIDACIONES`)

| Operación | Dueño | Recepción | Odontólogo |
|---|---|---|---|
| `GET /api/os/cobertura` | sí | sí | sí |
| `POST /api/liquidaciones` | sí | sí | 403 |
| `GET /api/liquidaciones[/{id}]` | sí | sí | sí |
| `PATCH` débitos | sí | sí | 403 |
| `POST /{id}/cerrar` y `/{id}/resultado` | sí | sí | 403 |
| `DELETE /{id}` (anular) | sí | sí | 403 |
| `GET /{id}/exportar` (`Accion.EXPORTAR`) | sí | sí | 403 |

## Casos borde
- **Arancel vencido**: se usa el último arancel cargado con `arancel_vencido = true` y `advertencia` (D2); la marca queda congelada en el detalle.
- **Cobertura futura** (`vigencia_desde > fecha`): se trata como `sin_cobertura` con advertencia de la fecha de inicio, nunca como vencida.
- **Turno reprogramado**: el original queda `reprogramado` (excluido); el turno nuevo, cuando se `finaliza`, entra en el período de su propio `inicio`. No hay doble cómputo.
- **Turno cancelado o ausente**: excluido por el filtro `estado = 'finalizado'`; al ser `finalizado` terminal, un turno ya incluido no puede invalidarse después.
- **Doble liquidación**: un turno ya reclamado **queda fuera** del borrador nuevo (no es error) y se informa en `advertencias` (D9); el `409` queda para un **segundo borrador de la misma OS/período** y para la carrera entre dos altas; tras anular, el turno queda libre.
- **Período ya cerrado / complementaria**: se permite una nueva liquidación aunque el período tenga una `pagada`, pero **sólo** con los turnos que nunca fueron reclamados por esa OS/período (D9); los turnos ya reclamados quedan afuera y se informan en `advertencias`; si no queda ninguno, el alta responde `422` ("no hay turnos nuevos para liquidar en ese período") y no se crea una liquidación vacía.
- **Corrida entre dos altas**: dos `POST /api/liquidaciones` simultáneos para la misma OS/período → uno crea el borrador y el otro recibe `409` por la violación del índice `uq_liquidacion_os_borrador`, traducida desde el `IntegrityError` con SAVEPOINT (`session.begin_nested()`), nunca `500` (D11).
- **Borde exacto del período**: el rango es UTC semiabierto `[primer día del período, primer día del período siguiente)`. Un turno iniciado exactamente a las `00:00` del día 1 pertenece al período; uno iniciado a las `00:00` del primer día del período siguiente ya pertenece al período siguiente y no entra. La fecha de referencia de la cobertura es la de cada turno, no la del período (D1/D2).
- **Borrador vacío**: no se puede presentar (`422`), defensivo aunque el alta ya rechaza períodos sin turnos.
- **Turno de otra OS**: la membresía exige convenio con la OS liquidada; los turnos sin convenio se informan en `turnos_sin_cobertura` y no se incluyen.
- **Liquidación de otro tenant**: `404` sin filtrar existencia (`R4`).

## Risks / Trade-offs
- **[Riesgo: cobertura cambiada a mitad de período]** → Se resuelve por la fecha de cada turno y se congela `arancel_vencido` en el detalle; el total es reproducible al regenerar el borrador.
- **[Riesgo: liquidaciones presentadas quedan desactualizadas si se corrige un arancel]** → Son inmutables por diseño; el ajuste de una liquidación ya presentada queda fuera de alcance en v1 (ver Supuestos) y la complementaria de D6 sólo cubre los turnos nunca reclamados.
- **[Riesgo: `vigente` derivado se desincronice]** → Sólo el servicio de liquidaciones transiciona estados; test explícito de que `pagada`/`anulada` ponen `vigente = false` en todo el detalle.
- **[Riesgo: `reclamado` derivado se desincronice y habilite un reclamo doble]** → `reclamado` se mantiene en la misma transacción que la transición de estado (la anulación lo pasa a `false`) y el índice único parcial `uq_liquidacion_detalle_turno_reclamado` es la garantía final: aunque la app quedara desfasada, la DB rechaza el segundo reclamo (D9, D12).
- **[Riesgo: el pago de la OS no impacta en caja]** → Fuera de alcance v1; queda documentado como supuesto para no dar una falsa sensación de conciliación automática.
- **[Trade-off: export sin datos del paciente]** → Menos útil si una OS exige padrón; se prioriza `R9` (mínimo necesario) y se extiende sólo con un requisito explícito.

## Migration Plan
1. `src/backend/alembic/versions/012_obras_sociales_liquidacion.py` con `revision = "012_obras_sociales_liquidacion"` y `down_revision = "011_mercadopago_webhooks"`: crea `liquidacion_os` y `liquidacion_detalle` con sus constraints e índices parciales, y en Postgres ejecuta `GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE liquidacion_os, liquidacion_detalle TO turnos_app`.
2. Registrar los modelos en `src/backend/alembic/env.py` y en `tests/conftest.py` (import del módulo y limpieza en orden inverso a las FK: `liquidacion_detalle`, `liquidacion_os`, luego `turno`).
3. Tests: esquema desplegado, strings de `GRANT/REVOKE`, y round-trip `upgrade head` → `downgrade 011_mercadopago_webhooks` → `upgrade head` sobre SQLite (mismo patrón que `test_migracion_010_caja_senas.py`).
4. Rollback: `alembic downgrade 011_mercadopago_webhooks` (revoca permisos, elimina índices y tablas). No hay migración de datos ni cambios en tablas existentes, por lo que el rollback es seguro en cualquier punto.
5. **Migración correctiva** `src/backend/alembic/versions/013_liquidacion_claim_unico.py` (`revision = "013_liquidacion_claim_unico"`, `down_revision = "012_obras_sociales_liquidacion"`): **no se modifica la `012`** (ya aplicada en bases existentes). Agrega `liquidacion_detalle.reclamado BOOLEAN NOT NULL DEFAULT true` con backfill portable en Python vía `op.get_bind()` (los reclamos de liquidaciones `anulada` y los reclamos duplicados preexistentes del mismo `tenant_id`/`turno_id`/`lower(obra_social)`/`periodo` en liquidaciones no anuladas pasan a `reclamado = false`, conservando el más antiguo por `(created_at, id)` y registrando el conteo en el log), agrega `liquidacion_os.turnos_sin_cobertura INTEGER NOT NULL DEFAULT 0`, y reemplaza los índices `uq_liquidacion_detalle_turno_abierto` y `uq_liquidacion_os_borrador` por `uq_liquidacion_detalle_turno_reclamado` y `uq_liquidacion_os_borrador` con la expresión `lower(obra_social)` (D9, D12). El metadata del ORM (`app/domain/liquidacion_os.py`) se actualiza en el mismo change, porque los tests construyen el esquema con `Base.metadata.create_all` y no con Alembic. Rollback: `downgrade()` revierte los índices y dropea las dos columnas, dejando la `012` intacta.

## Supuestos
- Los débitos de la OS se informan **por turno** (el modelo del §04 sólo define `debito_motivo` a nivel de detalle); un débito global se distribuye manualmente entre turnos.
- El pago de la OS no genera `MovimientoCaja` en v1.
- "Recepción" puede exportar liquidaciones porque §03 le da CRUD sobre ellas y es el rol que liquida; si el Dueño quiere restringirlo, es un cambio de matriz de una línea.
- `periodo` es siempre calendario UTC, coherente con `Turno.inicio`.
- Una liquidación **presentada** o **pagada** no se anula en v1: sólo se anula un `borrador` (baja lógica, `R7`). En consecuencia, el ajuste de una liquidación ya presentada o pagada (por ejemplo, un reclamo corregido) queda **fuera de alcance en v1** y se resuelve en v2 con un mecanismo de ajuste explícito; la complementaria de D6 cubre únicamente los turnos nunca reclamados.
- El reclamo de un turno es único por obra social y período mientras la liquidación no esté `anulada` (D9): anular un borrador es la única forma de liberar un turno ya reclamado.
