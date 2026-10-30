# Design

## Context

Ver `proposal.md` para la motivación y `specs/pacientes/spec.md` para los requerimientos normativos. Estado actual relevante del repositorio:

- `BaseRepository[T]` (`app/infrastructure/db/repository.py`) abstrae el acceso a datos aplicando automáticamente el filtro por `tenant_id` y levantando `TenantContextoRequerido` si no se dispone del contexto del consultorio.
- `Recurso.PACIENTES` ya está registrado en `app/domain/rbac.py` con permisos `CRUD` para `dueno` y `recepcion`, y `SOLO_LECTURA` (`Accion.LEER`) para `odontologo`.
- Las migraciones previas son `001_initial_tenant_usuario_auditoria`, `002_sesiones_tokens_publicos` y `003_catalogo_configuracion` (`revision = "003_catalogo_configuracion"`). Por ende, la migración de este change debe ser `004_pacientes_ficha_clinica` con `down_revision = "003_catalogo_configuracion"`.

## Goals / Non-Goals

**Goals:**
- Implementar los modelos de dominio `Paciente` y `FichaClinica` con constraints de base de datos (`UniqueConstraint("tenant_id", "dni")`, `UniqueConstraint("paciente_id")`) y schemas Pydantic estrictos (`extra='forbid'`, R1).
- Garantizar la creación atómica de la `FichaClinica` 1:1 en el alta de cada `Paciente`.
- Exponer endpoints REST en `/api/pacientes` con búsqueda por DNI o teléfono, baja lógica (`activo = False`, R7) y trazabilidad completa en `auditoria`.
- Proveer endpoint específico `PATCH /api/pacientes/:id/optin` para gestión rápida de opt-in y baja STOP.
- Proveer método/servicio de `get_or_create` por DNI para resolver el alta implícita en la reserva pública sin login (requisito para C-06 y C-15).
- Implementar la función de dominio para evaluar la regla RN-CO-01 (`puede_enviar_whatsapp(paciente)`).

**Non-Goals:**
- Carga de antecedentes, evoluciones u odontograma clínico detallado (corresponde a C-09 `historia-clinica-odontograma`).
- Envío real de mensajes WhatsApp vía Meta Cloud API o workers Celery/Redis (corresponde a C-08 `comunicaciones-mensajeria`).
- Pantallas o formularios de UI (corresponde a C-15 y C-16).

## Decisions

### D1 — Unicidad compuesta (`tenant_id`, `dni`) y normalización de DNI
Se define `UniqueConstraint("tenant_id", "dni", name="uq_paciente_tenant_dni")`. El DNI se almacena como string limpio (sin puntos ni espacios) para evitar duplicados por formato. En los schemas Pydantic se normaliza automáticamente el DNI removiendo puntos, guiones y espacios en blanco.
*Alternativa considerada*: Unicidad global de DNI. Descartada porque en un sistema SaaS multi-tenant un mismo paciente puede atenderse en consultorios distintos e independientes.

### D2 — Relación 1:1 atómica con `FichaClinica`
Toda creación de `Paciente` genera en la misma transacción su correspondiente `FichaClinica` con `paciente_id = paciente.id` y `tenant_id = paciente.tenant_id`. La tabla `ficha_clinica` posee `UniqueConstraint("paciente_id", name="uq_ficha_clinica_paciente_id")` y `ForeignKey("paciente.id", ondelete="CASCADE")`.
*Alternativa considerada*: Crear la ficha clínica de forma perezosa (lazy) en la primera consulta médica. Descartada para simplificar consultas, garantizar integridad referencial y evitar condiciones de carrera en C-09.

### D3 — Schemas Pydantic con `extra='forbid'` (R1) y sin `tenant_id` en el body (R4)
Los inputs `PacienteCreate`, `PacienteUpdate`, `PacienteOptinUpdate` rechazan campos desconocidos (`extra='forbid'`) y prohíben la inyección de `tenant_id` en el body. El `tenant_id` proviene siempre del token JWT autenticado (o del tenant público en reserva).

### D4 — Baja lógica uniforme (`activo = False`) con auditoría (R7)
El borrado de pacientes se realiza únicamente mediante baja lógica (`activo = False`). Se prohíbe el `DELETE` físico en la API. Toda baja o modificación de paciente se registra en la tabla `auditoria` indicando el actor, la acción y los valores anteriores y posteriores.

### D5 — Regla de negocio RN-CO-01 encapsulada en el dominio
Se implementa la función pura `puede_enviar_whatsapp(paciente: Paciente, es_transaccional_critico: bool = False) -> bool`. Si `optin_wa` es `False`, retorna `False` salvo que se trate de un mensaje transaccional legalmente exigido (RN-CO-01). El procesamiento de un comando "STOP" invoca la actualización de `optin_wa = False`, cortando inmediatamente todo envío futuro.

### D6 — Numeración de migración Alembic
Se nombra `004_pacientes_ficha_clinica.py` con `down_revision = "003_catalogo_configuracion"`. Concede permisos `SELECT, INSERT, UPDATE, DELETE` al rol de aplicación `turnos_app` condicionado a Postgres.

## Risks / Trade-offs

- **[Colisión de numeración con texto histórico de CHANGES.md]** → `CHANGES.md` mencionaba migración 003 antes de crearse la migración de catálogo. La secuencia real es `004_pacientes_ficha_clinica`; se documenta claramente.
- **[Aislamiento en búsquedas por teléfono o DNI]** → Los índices `ix_paciente_tenant_dni` y `ix_paciente_tenant_telefono` incluyen `tenant_id` como primer término para asegurar que las búsquedas sean rápidas y jamás lean datos fuera del consultorio.
