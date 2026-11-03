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

- [ ] 3.1 **Alta del borrador coleccionando turnos `finalizado` del período** (TDD)
  - Implementar `generar_borrador` en `src/backend/app/application/liquidaciones.py`: buscar turnos `finalizado` con `inicio` en el rango del período, resolver cobertura en lote (D1), incluir sólo prestaciones con convenio de la OS, calcular `monto_reclamado` y `total`, devolver `turnos_sin_cobertura` y `advertencias`.
  - Verificar con `tests/test_liquidaciones_negocio.py`: incluye sólo los finalizados del período; excluye `pendiente`/`confirmado`/`presente`/`cancelado`/`ausente`/`reprogramado`; excluye turnos de otro período; informa turnos sin cobertura; `422` sin turnos; `409` si ya existe borrador de la misma OS/período; `404` para prestaciones/turnos de otro tenant.

- [ ] 3.2 **Registro de débitos sobre el borrador y recálculo de totales** (TDD)
  - Implementar `registrar_debitos`: validar estado `borrador`, exigir `debito_motivo` cuando hay recorte, actualizar `monto_reconocido` por `turno_id`, recalcular `total` y `total_reconocido` en servidor y auditar (`accion="liquidacion.debitos"`, `RN-SE-01`).
  - Verificar con `tests/test_liquidaciones_negocio.py`: débito con motivo actualiza totales y deja evento de auditoría sin identificadores de paciente; débito sin motivo → `422`; `monto_reconocido` mayor al reclamado → `422`; edición sobre `presentada` → `409`.

- [ ] 3.3 **Presentación del borrador y registro del resultado de la OS** (TDD)
  - Implementar `presentar_liquidacion` (`borrador → presentada`, exige ≥1 turno y fija `presentada_por`/`presentada_at`) y `registrar_resultado` (`presentada → pagada | con_debitos`, guarda reconocidos, motivos, `total_reconocido` y `resuelta_por`/`resuelta_at`), validando el grafo de D4 y la coherencia entre `resultado` y los montos.
  - Verificar con `tests/test_liquidaciones_estados.py`: cierre exitoso; borrador vacío → `422`; resultado con recortes → `con_debitos`; resultado con total reconocido → `pagada`; `resultado = pagada` con montos reconocidos menores → `422`; transición inválida (p. ej. `borrador → pagada`) → `409`; eventos de auditoría de presentación y resultado.

- [ ] 3.4 **Anulación por baja lógica y liberación del turno** (TDD)
  - Implementar `anular_liquidacion` (`borrador → anulada` con motivo obligatorio, `vigente = false` en todo el detalle, auditoría con `antes`/`despues`) y el flip de `vigente` a `false` al pasar a `pagada`.
  - Verificar con `tests/test_liquidaciones_estados.py`: anular borrador conserva cabecera y detalle, deja `anulada_motivo` y habilita re-liquidar el turno; `409` al anular `presentada`/`pagada`/`con_debitos`; `pagada` pone `vigente = false` en todos los detalles; no se ejecuta ningún `DELETE` físico (el detalle sigue existiendo).

- [ ] 3.5 **Constraint de doble liquidación del mismo turno (`RN-OS-02`)** (TDD)
  - Verificar la garantía en las dos capas: rechazo `409` en el caso de uso y violación de `uq_liquidacion_detalle_turno_abierto` al insertar el detalle por segunda vez vía ORM.
  - Verificar con `tests/test_liquidaciones_unicidad.py`: dos borradores de la misma OS/período → `409` en el segundo; mismo turno en liquidaciones de OS distintas → permitido; mismo turno en períodos distintos → permitido; tras anular, el mismo turno entra en una nueva liquidación; inserción directa duplicada lanza `IntegrityError`.

## 4. API, RBAC y exportación

- [ ] 4.1 **Router `/api/liquidaciones` completo, matriz RBAC y registro en `main.py`** (TDD)
  - Crear `src/backend/app/api/routers/liquidaciones.py` con `POST/GET/GET {id}/PATCH`, `POST /{id}/cerrar`, `POST /{id}/resultado`, `DELETE /{id}` (body `{motivo}`) y `GET /{id}/exportar`, tomando `tenant_id` y actores del JWT (`R4`). Ajustar `MATRIZ[Recurso.LIQUIDACIONES]` a `Dueño: CRUD + EXPORTAR`, `Recepción: CRUD + EXPORTAR`, `Odontólogo: SOLO_LECTURA` (D8) y montar el router en `main.py` y en `tests/conftest.py`.
  - Verificar con `tests/test_liquidaciones_api.py`: ciclo completo `POST → PATCH → /cerrar → /resultado → DELETE` sobre otro borrador; `403` para Odontólogo en crear/editar/presentar/anular/exportar y `200` en `GET`; `404` para liquidaciones de otro tenant; `409` por doble borrador; `422` por período inválido; respuesta con `detalles` y `arancel_vencido` por fila.
  - Actualizar `tests/test_rbac_matriz.py` con los permisos nuevos de exportación sobre `LIQUIDACIONES`.

- [ ] 4.2 **Exportación CSV y JSON generada en servidor (`RN-OS-03`, `R8`, `R9`)** (TDD)
  - Implementar `exportar_liquidacion` (D7): CSV UTF-8 con BOM, separador `,`, decimal `.`, quoting RFC 4180 y una fila por turno con montos y `debito_motivo`; JSON con cabecera + detalle y `Decimal` como string. `Content-Disposition: attachment; filename="liquidacion-{os}-{periodo}.{ext}"`.
  - Verificar con `tests/test_liquidaciones_export.py`: CSV de una liquidación `con_debitos` incluye el `debito_motivo` y no incluye DNI/teléfono del paciente; JSON incluye cabecera y las tres filas; `formato=xml` → `422`; `403` para Odontólogo; el contenido no depende de parámetros de monto enviados por el cliente.

## 5. Integración, calidad y documentación

- [ ] 5.1 **Verificación integral del change** (calidad)
  - Ejecutar `pytest` completo (con `DATABASE_URL_TEST` apuntando al Postgres del contenedor, `R11`), `ruff check .` y `mypy src/backend`; confirmar suite previa sin regresiones y cobertura de los nuevos módulos.
  - Verificar además que `openspec validate c-13-obras-sociales-liquidacion --strict` siga en verde.

- [ ] 5.2 **Documentación del change y corrección de `CHANGES.md`**
  - Documentar los endpoints nuevos en `README.md` y en la sección correspondiente de `CHANGES.md`; corregir la línea "Migración 011: tablas `liquidacion_os`, `liquidacion_detalle`" del bloque `[C-13]` para que diga `012_obras_sociales_liquidacion` y refleje los estados reales (`borrador`, `presentada`, `pagada`, `con_debitos`, `anulada`).
  - Verificar que la sección `[C-13]` de `CHANGES.md` y el `README.md` mencionen `/api/os/cobertura`, `/api/liquidaciones`, `/cerrar`, `/resultado`, `/exportar` y que no quede ninguna referencia a la migración `011` como parte de este change.

## Workflow follow-up

- Revisar con `code-review` (governance `MEDIO`) antes de archivar.
- Archivar el change con `/opsx:archive c-13-obras-sociales-liquidacion` una vez verificada la suite completa.
- Push a GitHub al cerrar el change (`R12`).
