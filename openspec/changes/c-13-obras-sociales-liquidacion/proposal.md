# Proposal: `c-13-obras-sociales-liquidacion`

## Why
`C-04` ya administra el padrón de convenios (`CoberturaOS`) y `C-10`/`C-11` ya calculan cobertura y saldo por turno, pero el consultorio no puede **cerrar un período por obra social, controlar débitos ni exportar la presentación** (`US-040`, `US-041`, Flujo 5). Hoy ese trabajo vive en una planilla paralela: se pierde trazabilidad de lo reclamado contra lo reconocido, no hay garantía de que un turno no se liquide dos veces (`RN-OS-02`) y el arancel vencido se aplica en silencio (`RN-OS-01`). Este change cierra la Épica 5 del MVP y es prerequisito de `C-14` (exportación y auditoría del Dueño).

## What Changes
- **Resolución de cobertura compartida (`RN-OS-01`, `R8`)**: extraer el cálculo de cobertura/vigencia de arancel que hoy vive dentro de `calcular_montos_item_presupuesto` (`src/backend/app/application/presupuestos.py`) a un servicio reutilizable `app/application/cobertura.py`. `C-10` (presupuestos) y `C-11` (saldo de atención) pasan a consumirlo sin cambiar su comportamiento ni su firma pública. Se agrega el estado de arancel (`vigente`, `vencido`, `sin_cobertura`) que hoy no se expone.
- **Lookup de cobertura para agenda y cobro (`US-040`)**: `GET /api/os/cobertura` devuelve `precio_particular`, `cobertura`, `monto_a_cargo` y la advertencia de arancel vencido para una prestación + obra social + fecha de referencia (o turno). Sin cobertura vigente responde modo particular. No duplica el CRUD de `CoberturaOS` (`/api/admin/coberturas`).
- **Modelos y migración `012_obras_sociales_liquidacion`**: `LiquidacionOS` (cabecera por obra social + período `yyyymm`) y `LiquidacionOSDetalle` (una fila por turno con `monto_reclamado`, `monto_reconocido` y `debito_motivo`), con constraint de unicidad parcial que impide que un turno figure en dos liquidaciones abiertas de la misma OS/período (`RN-OS-02`).
- **Ciclo de vida de la liquidación (`US-041`)**: `borrador → presentada → pagada | con_debitos`, más `anulada` para la baja lógica de un borrador (`R7`, nunca hard delete). Los débitos se cargan sobre el borrador; al presentar, el detalle queda inmutable.
- **Endpoints `/api/liquidaciones`**: alta del borrador coleccionando turnos `finalizado` del período, listado, consulta, edición de débitos, `POST /{id}/cerrar` (presentación), `POST /{id}/resultado` (respuesta de la OS), `DELETE /{id}` (anulación) y `GET /{id}/exportar?formato=csv|json`.
- **Exportación en servidor (`RN-OS-03`, `R8`)**: CSV/JSON generados en backend con el detalle por turno y sus débitos; sin presentación electrónica (v2).
- **Auditoría (`RN-SE-01`)**: alta, débitos, presentación, resultado y anulación dejan evento en `Auditoria`.

## Capabilities

### New Capabilities
- `obras-sociales-liquidacion`: resolución de cobertura de obra social por arancel vigente con alerta de arancel vencido, y liquidación mensual por OS con control de débitos, estados, unicidad de turno liquidado y exportación CSV/JSON (`RN-OS-01`, `RN-OS-02`, `RN-OS-03`, `US-040`, `US-041`, Flujo 5).

### Modified Capabilities
- Ninguna. `presupuestos-planes` y `caja-senas` conservan sus requisitos: `C-13` sólo extrae la lógica compartida sin alterar el contrato observable de sus endpoints.

## Impact
- **Governance**: `MEDIO` (lógica de negocio de facturación a obras sociales, sin movimiento de dinero propio ni PHI nueva).
- **Dependencias**: `C-04` (`catalogo-configuracion`, padrón `CoberturaOS`) y `C-06` (`agenda-turnos`, estado `finalizado`); ambas archivadas. Reutiliza lógica de `C-10` y `C-11`.
- **Código afectado**: `src/backend/app/{domain,application,api}/` (nuevos `liquidacion_os.py`, `cobertura.py`, `liquidaciones.py`, `schemas_liquidaciones.py`, `routers/liquidaciones.py`), `src/backend/app/domain/rbac.py` (permiso de exportación sobre `Recurso.LIQUIDACIONES`), `src/backend/app/main.py`, `src/backend/alembic/env.py`, `tests/conftest.py`, `tests/` (nuevos test files), `CHANGES.md` (corregir la referencia "Migración 011" a `012`).
- **Migración**: `012_obras_sociales_liquidacion` (`down_revision = "011_mercadopago_webhooks"`), reversible, con `GRANT/REVOKE` para el rol `turnos_app`.
- **Desbloquea**: `C-14` (`auditoria-exportacion`), que exporta liquidaciones junto con agenda/pacientes/caja.
