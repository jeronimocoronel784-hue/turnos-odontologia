# core-models-multitenant Specification

## Purpose

Establece las entidades raíz multi-tenant del SaaS odontológico (Tenant, Usuario y Auditoría append-only) con aislamiento garantizado por tenant desde el primer día.

## Requirements

### Requirement: Tenant con slug único global

El sistema SHALL modelar cada consultorio como un `Tenant` con `slug` único global y `politicas` jsonb (anticipación mínima, seña default, cancelación); toda tabla de negocio SHALL llevar `tenant_id`.

#### Scenario: Alta de tenant piloto

- **Dado** que no existe un tenant con slug `consultorio-piloto`
- **Cuando** se crea el tenant con nombre y políticas por defecto
- **Entonces** el tenant queda persistido con su slug y sus políticas, y el seed lo marca como tenant por defecto

#### Scenario: Slug duplicado rechazado

- **Dado** que ya existe un tenant con slug `consultorio-piloto`
- **Cuando** se intenta crear otro tenant con el mismo slug
- **Entonces** la operación se rechaza por violación de unicidad con un mensaje en rioplatense, sin crear registros parciales

### Requirement: Usuario con email único por tenant y matrícula según rol

El sistema SHALL exigir email único dentro de cada tenant (constraint (`tenant_id`, `email`)), rol del enum dueno/recepcion/odontologo, y `matricula` obligatoria cuando el rol es odontologo. El `tenant_id` efectivo para cualquier operación SHALL provenir del token JWT, NUNCA del body o query del cliente.

#### Scenario: Alta feliz de usuaria recepcionista

- **Dado** el tenant piloto existente
- **Cuando** se crea una usuaria con rol recepcion, email nuevo y sin matrícula
- **Entonces** queda persistida como miembro de ese tenant con rol recepcion

#### Scenario: Email duplicado en el mismo tenant rechazado

- **Dado** que en el tenant A ya existe un usuario con email `recepcion@ejemplo.com`
- **Cuando** se intenta crear otro usuario con ese mismo email en el tenant A
- **Entonces** la operación se rechaza por unicidad con un mensaje en rioplatense que indica qué hacer

#### Scenario: Mismo email en otro tenant permitido (borde multi-tenant)

- **Dado** que en el tenant A existe un usuario con email `recepcion@ejemplo.com`
- **Cuando** se crea un usuario con ese mismo email en el tenant B
- **Entonces** la operación tiene éxito, porque la unicidad es por (`tenant_id`, `email`) y no global

#### Scenario: Odontólogo sin matrícula rechazado (error de negocio)

- **Dado** el tenant piloto existente
- **Cuando** se intenta crear un usuario con rol odontologo sin informar matrícula
- **Entonces** la validación rechaza la operación con un mensaje en rioplatense que pide la matrícula profesional

### Requirement: Aislamiento total por tenant

El sistema SHALL garantizar que ninguna consulta de negocio devuelva filas de otro tenant; ver filas del tenant equivocado es un bug CRITICAL que bloquea el change.

#### Scenario: Tenant A no ve datos del tenant B

- **Dado** que existen usuarios en los tenants A y B
- **Cuando** se listan los usuarios en el contexto del tenant A
- **Entonces** solo aparecen los usuarios del tenant A y ninguno del tenant B

#### Scenario: Filtro de tenant en repositorios base

- **Dado** cualquier repositorio que hereda de `BaseRepository`
- **Cuando** se ejecuta una consulta sin especificar tenant
- **Entonces** el repositorio aplica el `tenant_id` del contexto actual y jamás devuelve datos sin filtro de tenant

### Requirement: Auditoría append-only con retención de 5 años

La tabla `auditoria` SHALL aceptar solo INSERT y SELECT; cualquier intento de UPDATE o DELETE SHALL ser rechazado a nivel de permiso de base de datos, y los registros SHALL conservarse un mínimo de 5 años.

#### Scenario: UPDATE sobre auditoría rechazado (borde)

- **Dado** un registro existente en `auditoria`
- **Cuando** se intenta modificarlo con UPDATE o eliminarlo con DELETE
- **Entonces** la base de datos rechaza la operación por permiso insuficiente y el registro queda intacto

#### Scenario: Cambio crítico deja rastro auditable

- **Dado** un usuario del tenant A autenticado
- **Cuando** crea o modifica un usuario del tenant A
- **Entonces** queda un registro en `auditoria` con actor, acción, entidad, valores antes/después y timestamp

### Requirement: Seed mínimo del piloto con datos ficticios

El sistema SHALL proveer un seed con 1 tenant piloto, 1 usuario Dueño y la matriz de permisos base, usando SIEMPRE datos sintéticos (R13: jamás datos reales de pacientes o personas).

#### Scenario: Seed en base vacía

- **Dado** una base de datos migrada pero vacía
- **Cuando** se ejecuta el seed
- **Entonces** existen exactamente 1 tenant, 1 usuario Dueño activo y los permisos base, todos con datos ficticios identificables como tales
