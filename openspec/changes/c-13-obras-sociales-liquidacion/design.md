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

### D4. Modelo de estados con `anulada` para cumplir `R7`
- **Decisión**: `EstadoLiquidacionOS = borrador | presentada | pagada | con_debitos | anulada`, con grafo:
  - `borrador → presentada | anulada`
  - `presentada → pagada | con_debitos`
  - `con_debitos → pagada` (la OS termina pagando el saldo reconocido)
  - `pagada` y `anulada` terminales.
- **Razón**: el KB enumera 4 estados y `DELETE` es parte del "CRUD" pedido, pero `R7` prohíbe hard delete en dominios de dinero. `anulada` es una baja lógica que conserva cabecera y detalle y libera los turnos (`vigente = false`).
- **Alternativas descartadas**: (a) borrado físico del borrador — viola `R7`; (b) columna `deleted_at` sin estado — rompe el grafo explícito que el resto del proyecto usa (`Sena`, `Presupuesto`, `Turno`).

### D5. Membresía de turnos derivada del período, inmutable
- **Decisión**: el borrador se arma una sola vez con los turnos `finalizado` cuyo `inicio` cae en `[primer día del período, primer día del período siguiente)` en UTC y cuya prestación tiene convenio con la OS. No se agregan ni quitan turnos manualmente; para corregir se anula el borrador y se regenera.
- **Razón**: `finalizado` es estado terminal en el grafo de turnos, así que la membresía no puede invalidarse después. Editar la membresía manualmente abriría la puerta a liquidar turnos no finalizados por la puerta de atrás.
- **Alternativas descartadas**: `POST /{id}/detalles` — descartado por scope creep y por romper la derivación determinística período→turnos.

### D6. Liquidaciones complementarias por período (período ya cerrado)
- **Decisión**: se permite más de una liquidación por OS/período (p. ej. un turno finalizado tarde o un ajuste tras un pago). Lo único bloqueado es **un segundo `borrador` simultáneo** para la misma OS/período (índice único parcial `uq_liquidacion_os_borrador`). Si el período ya tiene una liquidación `pagada`, el alta devuelve una advertencia "esta liquidación se tratará como complementaria".
- **Razón**: bloquean el caso de negocio real sin renunciar al constraint de `RN-OS-02` (que es por turno, no por período).
- **Alternativas descartadas**: (a) único por OS/período — impide el ajuste; (b) sin límite de borradores — permite crear N borradores duplicados por error.

### D7. Exportación en servidor sin PHI innecesaria (`RN-OS-03`, `R8`, `R9`)
- **Decisión**: `GET /api/liquidaciones/{id}/exportar?formato=csv|json` arma el contenido en backend y lo devuelve con `Content-Disposition`. Columnas: `periodo, obra_social, estado, estado_arancel, turno_id, fecha_turno, prestacion, monto_reclamado, monto_reconocido, debito_motivo`. CSV en UTF-8 con BOM, separador `,` y decimal `.` (RFC 4180).
- **Razón**: `R8` prohíbe cálculo en cliente y `R9` exige mínimo necesario: la OS necesita el turno y el monto, no el DNI ni el teléfono del paciente.
- **Alternativas descartadas**: (a) CSV con separador `;` y coma decimal (locale es-AR) — descartado por interoperabilidad con planillas de OS y parsers; (b) incluir nombre/DNI del paciente — descartado por mínimo necesario (queda como posible extensión si una OS lo exige, y ahí se evalúa con governance HIGH).

### D8. Permiso de exportación explícito en la matriz RBAC
- **Decisión**: `MATRIZ[Recurso.LIQUIDACIONES]` pasa a `dueno: CRUD + EXPORTAR`, `recepcion: CRUD + EXPORTAR`, `odontologo: SOLO_LECTURA`. No se agrega `Accion` nueva: se reutiliza `Accion.EXPORTAR`.
- **Razón**: el odontólogo debe poder leer la cobertura de sus turnos, pero no exportar la liquidación del consultorio (la matriz de §03 le da exportación "parcial (clínica propia)"). La fila "Liquidaciones OS" de §03 dice CRUD para Dueño y Recepción, que son los roles que liquidan.
- **Alternativas descartadas**: (a) exigir además `Recurso.EXPORTACION` — el odontólogo también lo tiene y no filtra nada; (b) rol hardcodeado en el router — duplica la fuente de verdad del RBAC.

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
- `uq_liquidacion_os_borrador`: `UNIQUE (tenant_id, obra_social, periodo) WHERE estado = 'borrador'` (D6).
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
| `vigente` | BOOLEAN | `true` mientras la liquidación está abierta (D3) |
| `created_at` / `updated_at` | TIMESTAMPTZ | `AuditMixin` |

Constraints:
- `uq_liquidacion_detalle_turno`: `UNIQUE (liquidacion_id, turno_id)`.
- `uq_liquidacion_detalle_turno_abierto`: `UNIQUE (tenant_id, turno_id, obra_social, periodo) WHERE vigente`.
- `ck_liquidacion_detalle_montos`: `monto_reclamado >= 0 AND (monto_reconocido IS NULL OR (monto_reconocido >= 0 AND monto_reconocido <= monto_reclamado))`.
- `ck_liquidacion_detalle_debito_motivo`: `monto_reconocido IS NULL OR monto_reconocido = monto_reclamado OR (debito_motivo IS NOT NULL AND length(trim(debito_motivo)) > 0)`.
- `ck_liquidacion_detalle_periodo_largo`: `length(periodo) = 6`.

Índices: `ix_liquidacion_detalle_liquidacion_id`, `ix_liquidacion_detalle_tenant_turno`.

### Módulos
- `src/backend/app/domain/liquidacion_os.py`: enums, grafo (`es_transicion_liquidacion_valida`), helpers de período (`periodo_desde_fecha`, `rango_periodo`, `periodo_valido`) y modelos.
- `src/backend/app/application/liquidaciones.py`: casos de uso.
- `src/backend/app/application/cobertura.py`: loaders de cobertura (D1).
- `src/backend/app/api/schemas_liquidaciones.py` y `src/backend/app/api/routers/liquidaciones.py`.

## Contrato de endpoints

| Método | Ruta | Input | Output / errores |
|---|---|---|---|
| GET | `/api/os/cobertura` | query: `prestacion_id` (req), `obra_social?`, `fecha?`, `turno_id?`, `cantidad` (1..99) | `200 CoberturaLookupRead`; `404` prestación/turno inexistente en el tenant; `422` si `turno_id` y `prestacion_id` se contradicen |
| POST | `/api/liquidaciones` | `{obra_social, periodo, fecha_referencia?}` | `201 LiquidacionOSRead`; `409` si ya hay borrador de esa OS/período; `422` si no hay turnos finalizados con cobertura |
| GET | `/api/liquidaciones` | query `obra_social?`, `periodo?`, `estado?` | `200 list[LiquidacionOSRead]` |
| GET | `/api/liquidaciones/{id}` | — | `200 LiquidacionOSRead` con `detalles`; `404` fuera del tenant |
| PATCH | `/api/liquidaciones/{id}` | `{observaciones?, detalles: [{turno_id, monto_reconocido, debito_motivo?}]}` | `200 LiquidacionOSRead`; `409` si no está en `borrador`; `422` débito sin motivo |
| POST | `/api/liquidaciones/{id}/cerrar` | `{observaciones?}` | `200`; `409` estado inválido; `422` sin turnos |
| POST | `/api/liquidaciones/{id}/resultado` | `{resultado: pagada\|con_debitos, detalles: [{turno_id, monto_reconocido, debito_motivo?}]}` | `200`; `409`/`422` según grafo y coherencia de totales |
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

`LiquidacionOSRead` incluye cabecera + `total`, `total_reconocido`, `turnos_sin_cobertura`, `advertencias: [str]` y `detalles: [{turno_id, fecha_turno, prestacion, monto_reclamado, monto_reconocido, debito_motivo, arancel_vencido}]`. Todos los inputs usan `extra='forbid'` (`R1`); `tenant_id` y actores salen del JWT (`R4`); ningún schema de entrada acepta montos de totales (`R8`).

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
- **Doble liquidación**: `409` en aplicación + índice único parcial en DB (D3); tras anular, el turno queda libre.
- **Período ya cerrado / complementaria**: se permite una nueva liquidación aunque el período tenga una `pagada`; el alta devuelve advertencia de complementaria (D6).
- **Borrador vacío**: no se puede presentar (`422`), defensivo aunque el alta ya rechaza períodos sin turnos.
- **Turno de otra OS**: la membresía exige convenio con la OS liquidada; los turnos sin convenio se informan en `turnos_sin_cobertura` y no se incluyen.
- **Liquidación de otro tenant**: `404` sin filtrar existencia (`R4`).

## Risks / Trade-offs
- **[Riesgo: cobertura cambiada a mitad de período]** → Se resuelve por la fecha de cada turno y se congela `arancel_vencido` en el detalle; el total es reproducible al regenerar el borrador.
- **[Riesgo: liquidaciones presentadas quedan desactualizadas si se corrige un arancel]** → Son inmutables por diseño; la corrección se hace con una liquidación complementaria (D6) o anulando mientras siga en `borrador`.
- **[Riesgo: `vigente` derivado se desincronice]** → Sólo el servicio de liquidaciones transiciona estados; test explícito de que `pagada`/`anulada` ponen `vigente = false` en todo el detalle.
- **[Riesgo: el pago de la OS no impacta en caja]** → Fuera de alcance v1; queda documentado como supuesto para no dar una falsa sensación de conciliación automática.
- **[Trade-off: export sin datos del paciente]** → Menos útil si una OS exige padrón; se prioriza `R9` (mínimo necesario) y se extiende sólo con un requisito explícito.

## Migration Plan
1. `src/backend/alembic/versions/012_obras_sociales_liquidacion.py` con `revision = "012_obras_sociales_liquidacion"` y `down_revision = "011_mercadopago_webhooks"`: crea `liquidacion_os` y `liquidacion_detalle` con sus constraints e índices parciales, y en Postgres ejecuta `GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE liquidacion_os, liquidacion_detalle TO turnos_app`.
2. Registrar los modelos en `src/backend/alembic/env.py` y en `tests/conftest.py` (import del módulo y limpieza en orden inverso a las FK: `liquidacion_detalle`, `liquidacion_os`, luego `turno`).
3. Tests: esquema desplegado, strings de `GRANT/REVOKE`, y round-trip `upgrade head` → `downgrade 011_mercadopago_webhooks` → `upgrade head` sobre SQLite (mismo patrón que `test_migracion_010_caja_senas.py`).
4. Rollback: `alembic downgrade 011_mercadopago_webhooks` (revoca permisos, elimina índices y tablas). No hay migración de datos ni cambios en tablas existentes, por lo que el rollback es seguro en cualquier punto.

## Supuestos
- Los débitos de la OS se informan **por turno** (el modelo del §04 sólo define `debito_motivo` a nivel de detalle); un débito global se distribuye manualmente entre turnos.
- El pago de la OS no genera `MovimientoCaja` en v1.
- "Recepción" puede exportar liquidaciones porque §03 le da CRUD sobre ellas y es el rol que liquida; si el Dueño quiere restringirlo, es un cambio de matriz de una línea.
- `periodo` es siempre calendario UTC, coherente con `Turno.inicio`.
