# Proposal

## Why

La agenda y máquina de estados del turno son el corazón operativo del consultorio odontológico: sin control anti-solapamiento por profesional y sillón, respeto de bloqueos, grafo cerrado de estados y reserva online pública 24/7 vinculada a catálogo (`C-04`) y pacientes (`C-05`), no es posible operar la clínica ni habilitar los flujos asistenciales y financieros posteriores (`C-07` a `C-13`).

## What Changes

- Crear los modelos multi-tenant `Turno` y `Bloqueo` en `src/backend/app/domain/` (`turno.py`, `bloqueo.py`) con `TenantMixin`, `AuditMixin`, grafo cerrado de estados (`pendiente → confirmado → presente → finalizado` y ramas `pendiente|confirmado → cancelado|ausente|reprogramado`, RN-AG-07), cálculo de duración `fin = inicio + duracion_prestacion` salvo override explícito auditado (RN-AG-02), marca explícita `sobreturno` con motivo obligatorio (RN-AG-04) y vínculo de reprogramación `turno_origen_id` (RN-AG-06).
- Implementar la migración reversible `005_agenda_turnos.py` con las tablas `turno` y `bloqueo`, constraints de integridad (`fin > inicio`, `sobreturno` exige motivo/observaciones, al menos uno de `profesional_id` o `sillon_id` en `bloqueo`), índices de consulta (`(tenant_id, profesional_id, inicio)`, `(tenant_id, sillon_id, inicio)`, `(tenant_id, estado, inicio)`, `(tenant_id, desde, hasta)`) y `GRANT`/`REVOKE` CRUD para el rol `turnos_app`.
- Implementar la validación de anti-solapamiento de rangos `[inicio, fin)` por profesional y por sillón (RN-AG-01) y bloqueo de slots cubiertos por `Bloqueo` (RN-AG-03), devolviendo `409 Conflict` con mensaje accionable en español rioplatense y lista de slots alternativos cercanos cuando un horario ya está ocupado o bloqueado (RN-GL-02).
- Exponer los endpoints internos autenticados y protegidos por RBAC (`Recurso.AGENDA` y `Recurso.BLOQUEOS`):
  - `GET /api/agenda` (vista diaria/semanal filtrable por profesional, sillón y estado, con turnos y bloqueos).
  - `POST /api/turnos`, `GET /api/turnos/{id}`, `PATCH /api/turnos/{id}/estado`, `POST /api/turnos/{id}/reprogramar` (1-clic que pasa el turno original a `reprogramado` y crea el nuevo con `turno_origen_id`, RN-AG-06).
  - `GET /api/bloqueos`, `POST /api/bloqueos`, `DELETE /api/bloqueos/{id}`.
- Exponer los endpoints públicos sin login (Flujo 1 y RN-SE-03):
  - `GET /reservar/{slug}` (catálogo público del consultorio + cálculo de slots reales disponibles descontando turnos activos y bloqueos).
  - `POST /reservar/{slug}` (alta o actualización implícita de `Paciente` vía `get_or_create_paciente`, creación de `Turno` en `pendiente`, emisión de `TokenGestion` atado a `recurso="turno"` y `recurso_id=str(turno.id)`, e indicador de seña pendiente si la prestación tiene `requiere_sena=True`).
  - `GET /mis-turnos/{token}`, `POST /mis-turnos/{token}/confirmar`, `POST /mis-turnos/{token}/cancelar` y `POST /mis-turnos/{token}/reprogramar` validando el token opaco con `validar_token_gestion` y respetando la política de anticipación mínima (`anticipacion_min_hs` / `cancelacion_hs` del tenant, RN-AG-05) y el bloqueo de confirmación cuando la prestación exige seña aún no cobrada (RN-PA-01).
- Registrar en `Auditoria` (append-only, RN-SE-01) toda creación, transición de estado, reprogramación, sobreturno y bloqueo.

## Capabilities

### New Capabilities
- `agenda-turnos`: Gestión integral de agenda odontológica multi-profesional y por sillón, máquina de estados del turno, control anti-solapamiento con sugerencia de slots alternativos, bloqueos horarios, reprogramación con trazabilidad y reserva/autogestión pública por token opaco.

### Modified Capabilities
<!-- Ninguna capacidad existente cambia sus requisitos a nivel spec -->

## Impact

- **Dominio y Aplicación**: nuevos módulos `src/backend/app/domain/turno.py`, `src/backend/app/domain/bloqueo.py` y `src/backend/app/application/agenda.py`.
- **Migraciones**: nueva migración `src/backend/alembic/versions/005_agenda_turnos.py` encadenada a `004_pacientes_ficha_clinica`.
- **API y Schemas**: nuevos módulos `src/backend/app/api/schemas_agenda.py`, `src/backend/app/api/routers/agenda.py` y `src/backend/app/api/routers/reserva_publica.py` registrados en `src/backend/app/main.py`.
- **Tests**: suite de tests de migración, reglas de negocio/máquina de estados, anti-solapamiento, endpoints internos RBAC y flujo público de reserva/gestión por token.
