# Proposal

## Why

El consultorio odontológico necesita gestionar el registro de pacientes sin exigirles crear una cuenta con contraseña (modelo sin login para reserva ágil, resuelta en PO), garantizando la unicidad de su identidad por consultorio mediante su DNI y el cumplimiento estricto de la regla de negocio RN-CO-01 que prohíbe el envío de mensajes automáticos por WhatsApp sin consentimiento expreso (opt-in). Asimismo, cada paciente debe contar desde su creación con una ficha clínica 1:1 lista para almacenar su historia y antecedentes clínicos.

## What Changes

- **Modelo `Paciente`**:
  - Clave única compuesta por consultorio: (`tenant_id`, `dni`).
  - Campo `optin_wa` de tipo booleano con valor por defecto `false`.
  - Campos `obra_social_id` y `nro_afiliado` como opcionales/nullables.
  - Campos de contacto e identificación: `nombre`, `dni`, `telefono`, `email` (nullable), `fecha_nac` (nullable), `observaciones` (nullable), `activo` (bool, default `true`).
  - Trazabilidad y aislamiento multi-tenant mediante `TenantMixin` y `AuditMixin`.
- **Modelo `FichaClinica`**:
  - Relación 1:1 con `Paciente` (`paciente_id` único, no nulo y FK a `paciente.id`).
  - Campos clínicos iniciales vacíos (`antecedentes`, `alergias`, `medicacion`, `habitos`, `datos_json`).
  - Aislamiento multi-tenant y timestamps de auditoría.
- **Migración Alembic `004_pacientes_ficha_clinica`**:
  - Creación de tablas `paciente` y `ficha_clinica` con constraints de unicidad (`uq_paciente_tenant_dni`, `uq_ficha_clinica_paciente_id`), FKs e índices de búsqueda (`ix_paciente_tenant_dni`, `ix_paciente_tenant_telefono`).
  - Permisos CRUD para el rol de aplicación `turnos_app`.
  - Reversibilidad completa con `downgrade`.
- **Schemas Pydantic (`extra='forbid'`, R1)**:
  - Schemas para creación, actualización, lectura y actualización de opt-in de pacientes con validaciones en español rioplatense.
- **Endpoints REST `/api/pacientes`**:
  - `GET /api/pacientes`: búsqueda y filtrado por DNI, teléfono o texto libre, y filtro de activos.
  - `GET /api/pacientes/{id}`: detalle de un paciente y su ficha clínica vinculada.
  - `POST /api/pacientes`: alta explícita de paciente con creación automática de su ficha clínica 1:1.
  - `PATCH /api/pacientes/{id}`: actualización de datos de contacto, obra social y afiliado.
  - `DELETE /api/pacientes/{id}`: baja lógica (`activo = false`, R7) con registro de auditoría.
  - `PATCH /api/pacientes/{id}/optin`: actualización directa del consentimiento de WhatsApp (alta y baja STOP).
- **Servicio / Lógica `get_or_create`**:
  - Soporte de alta implícita en flujo de reserva pública: si el paciente con ese DNI ya existe en el tenant, se actualizan sus datos de contacto; si no existe, se crea con su ficha clínica.
- **Cumplimiento RN-CO-01**:
  - Regla de negocio verificable para bloqueo de mensajes automáticos cuando `optin_wa = false` y corte inmediato ante comando STOP.

## Capabilities

### New Capabilities
- `pacientes`: Registro, búsqueda, deduplicación por DNI y gestión de consentimiento WhatsApp (opt-in/STOP) de pacientes, junto con la inicialización de su ficha clínica 1:1.

### Modified Capabilities
<!-- Ninguna capability existente modifica sus requerimientos -->

## Impact

- **Modelos**: Nuevos archivos `src/backend/app/domain/paciente.py` y `src/backend/app/domain/ficha_clinica.py`.
- **API**: Schemas en `src/backend/app/api/schemas_pacientes.py` y router en `src/backend/app/api/routers/pacientes.py`.
- **Infraestructura**: Migración Alembic `004_pacientes_ficha_clinica.py`.
- **Aplicación**: Registro del router en `src/backend/app/main.py`.
- **RBAC**: Permisos sobre `Recurso.PACIENTES` (Dueño/Recepción: CRUD, Odontólogo: Lectura).
- **Tests**: Suite completa de tests unitarios y de integración en `tests/test_pacientes.py` y verificación de migración en `tests/test_migracion_004_pacientes.py`.
