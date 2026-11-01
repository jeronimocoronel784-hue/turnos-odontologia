# Proposal: `c-10-presupuestos-planes`

## Why
El consultorio necesita presupuestar planes de tratamiento odontológico multi-etapa con cálculo automático de cobertura de obra social vs. importe a cargo del paciente (`RN-OS-01`, `R8`), validar que la aceptación de cualquier presupuesto que incluya prestaciones invasivas cuente con consentimiento informado firmado (`RN-CL-04`) y vincular las citas (`Turno`) al plan hasta el alta clínica (`US-022`).

## What Changes
- **Dominio y Migración `009_presupuestos_planes`**:
  - `Presupuesto` (`presupuesto`): cabecera con `paciente_id`, `obra_social` opcional, `estado` (`borrador`, `presentado`, `aceptado`, `rechazado`, `en_curso`, `finalizado`), `total`, `total_cobertura_os`, `total_a_cargo`, `validez_hasta`, `observaciones`, `created_by`.
  - `PresupuestoItem` (`presupuesto_item`): detalle con `presupuesto_id`, `prestacion_id`, `pieza_fdi` opcional (validada con `es_pieza_fdi_valida`), `cantidad`, `precio_unit`, `cobertura_os`, `a_cargo` (`a_cargo = precio_unit * cantidad - cobertura_os`, nunca negativo, calculado siempre en servidor según `R8`).
  - `PresupuestoTurno` (`presupuesto_turno`): tabla de asociación N–N entre `Presupuesto` y `Turno` (citas del plan de tratamiento, con `presupuesto_item_id` opcional).
  - Permisos `GRANT/REVOKE` para `turnos_app` en `009_presupuestos_planes.py`.
- **Reglas de Negocio (`RN-OS-01`, `RN-CL-04`, `R8`)**:
  - `calcular_montos_item_presupuesto`: busca `CoberturaOS` activa y vigente en la fecha del presupuesto para `(tenant_id, obra_social, prestacion_id)`. Si hay cobertura vigente, calcula `cobertura_os` y `a_cargo`; si no hay cobertura vigente o el paciente se atiende como particular, `cobertura_os = 0` y `a_cargo = precio_unit * cantidad` (`RN-OS-01`).
  - Grafo de estados de `Presupuesto`: `borrador -> presentado -> aceptado | rechazado`, `aceptado -> en_curso -> finalizado` (y transición directa `borrador -> aceptado` o `aceptado -> finalizado`).
  - Al aceptar (`aceptar_presupuesto`), si algún `PresupuestoItem` corresponde a una `Prestacion` con `invasiva = True`, verifica `tiene_consentimiento_vigente` (`C-09`) para cada prestación invasiva incluida; si falta alguno, rechaza con `409 Conflict` (`RN-CL-04`).
  - Vinculación de turnos al plan (`vincular_turno_a_presupuesto`): asocia un `Turno` del mismo paciente al `Presupuesto` y, si estaba en `aceptado`, lo pasa automáticamente a `en_curso`.
- **API REST (`/api/presupuestos`)**:
  - Protegidos por `Recurso.PRESUPUESTOS` (`DUENO`, `RECEPCION`, `ODONTOLOGO`: CRUD):
    - `GET /api/presupuestos`, `POST /api/presupuestos`, `GET /api/presupuestos/{id}`
    - `POST /api/presupuestos/{id}/items`
    - `POST /api/presupuestos/{id}/presentar`, `POST /api/presupuestos/{id}/aceptar`, `POST /api/presupuestos/{id}/rechazar`, `POST /api/presupuestos/{id}/finalizar`
    - `GET /api/presupuestos/{id}/turnos`, `POST /api/presupuestos/{id}/turnos`

## Capabilities
### New Capabilities
- `presupuestos-planes`: Presupuestos y planes de tratamiento con cálculo servidor de cobertura OS vs. particular (`RN-OS-01`, `R8`), exigencia de consentimiento firmado al aceptar prestaciones invasivas (`RN-CL-04`) y vinculación N–N con turnos hasta el alta.

## Impact
- **Governance**: `MEDIO` (implementamos con checkpoints y verificación TDD estricta).
- **Dependencias**: `C-04` (`catalogo-configuracion`), `C-06` (`agenda-turnos`), `C-09` (`historia-clinica-odontograma`). Desbloquea `C-16` (`frontend-agenda-clinica`).
