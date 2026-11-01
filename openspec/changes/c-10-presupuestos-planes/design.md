# Design: `c-10-presupuestos-planes`

## UI Mockups
Decision: no (no UI — este change implementa modelos, migración, lógica de negocio y endpoints backend de presupuestos y planes; la UI corresponde a C-16).

## Context
`C-10` implementa la gestión de presupuestos y planes de tratamiento (`US-022`) apoyándose en el catálogo de prestaciones y padrón `CoberturaOS` (`C-04`), la agenda de turnos (`C-06`) y los consentimientos informados e historia clínica (`C-09`).

## Decisions

### D1. Cálculo de montos exclusivamente en servidor (`R8`, `RN-OS-01`)
- Los schemas de entrada (`PresupuestoCreate`, `PresupuestoItemInput`) nunca reciben montos calculados por el cliente (`precio_unit`, `cobertura_os`, `a_cargo`, `total`): solo reciben `prestacion_id`, `pieza_fdi` (opcional) y `cantidad`.
- Para cada item, el servidor toma `precio_unit = prestacion.precio_particular`. Si el presupuesto indica `obra_social`, busca una fila en `cobertura_os` con `activa = True`, `obra_social` coincidente (case-insensitive) y `vigencia_desde <= fecha <= vigencia_hasta` (o `vigencia_hasta IS NULL`).
- Si hay cobertura vigente, `cobertura_unit = min(precio_unit, cobertura.arancel)` (o `max(Decimal("0.00"), precio_unit - cobertura.copago)` cuando el arancel cubre la prestación menos copago; adoptamos `cobertura_unit = min(precio_unit, cobertura.arancel)` de modo que `a_cargo = (precio_unit * cantidad) - (cobertura_unit * cantidad)` coincida exactamente con la fórmula canónica de `04_modelo_de_datos.md`: `a_cargo = precio_unit * cantidad - cobertura_os`). Si no hay cobertura vigente, `cobertura_os = 0.00` y se factura como particular (`RN-OS-01`).

### D2. Máquina de estados de `Presupuesto` y guardia `RN-CL-04`
- Estados (`EstadoPresupuesto`): `borrador`, `presentado`, `aceptado`, `rechazado`, `en_curso`, `finalizado`.
- Transiciones permitidas:
  - `borrador -> presentado | aceptado | rechazado`
  - `presentado -> aceptado | rechazado`
  - `aceptado -> en_curso | finalizado`
  - `en_curso -> finalizado`
- Al pasar a `aceptado`, se recorren los `PresupuestoItem` del presupuesto: por cada item cuya `Prestacion` tenga `invasiva == True`, se invoca `tiene_consentimiento_vigente(session, tenant_id=..., paciente_id=presupuesto.paciente_id, prestacion_id=item.prestacion_id)`. Si alguno devuelve `False`, se lanza `Conflicto` (`409`) con mensaje claro en español rioplatense (`RN-CL-04`).

### D3. Asociación N–N `PresupuestoTurno`
- La tabla `presupuesto_turno` vincula `(presupuesto_id, turno_id)` con `UniqueConstraint("presupuesto_id", "turno_id")` y `presupuesto_item_id` opcional.
- Al vincular un turno a un presupuesto en estado `aceptado`, el presupuesto transiciona automáticamente a `en_curso`.
