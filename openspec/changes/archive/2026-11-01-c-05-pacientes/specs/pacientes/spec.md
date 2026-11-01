# Spec Delta

## Purpose

Permite gestionar el registro, búsqueda, deduplicación y consentimiento de comunicación de los pacientes del consultorio odontológico sin requerir inicio de sesión, vinculando a cada uno una ficha clínica única 1:1.

## ADDED Requirements

### Requirement: Unicidad de DNI por consultorio
El sistema SHALL garantizar que la combinación de `tenant_id` y `dni` sea única, permitiendo que un mismo DNI exista en diferentes consultorios pero impidiendo duplicados dentro del mismo consultorio.

#### Scenario: Creación con DNI nuevo en el consultorio
- **WHEN** un usuario con rol autorizado crea un paciente con un DNI no registrado previamente en su consultorio
- **THEN** el sistema registra el paciente exitosamente con código HTTP 201 y asigna un identificador único

#### Scenario: Rechazo por DNI duplicado en el mismo consultorio
- **WHEN** se intenta crear un paciente con un DNI que ya existe para el mismo `tenant_id`
- **THEN** el sistema rechaza la operación con código HTTP 409 Conflicto y un mensaje explicativo en español rioplatense

#### Scenario: Mismo DNI en consultorios distintos permitido
- **WHEN** se registra un paciente con un DNI idéntico al de otro paciente pero perteneciente a un `tenant_id` diferente
- **THEN** el sistema permite el registro exitosamente en ambos consultorios de forma independiente

### Requirement: Ficha clínica 1:1 inicializada con el paciente
El sistema SHALL crear automáticamente una ficha clínica vacía vinculada de forma 1:1 a cada nuevo paciente en el momento de su alta.

#### Scenario: Creación implícita de ficha clínica
- **WHEN** se da de alta un nuevo paciente en el sistema
- **THEN** se crea de forma atómica una entidad `FichaClinica` con `paciente_id` correspondiente y campos clínicos inicializados vacíos

#### Scenario: Detalle de paciente incluye su ficha clínica
- **WHEN** se consulta el detalle de un paciente existente vía `GET /api/pacientes/:id`
- **THEN** la respuesta incluye los datos del paciente y la información básica de su ficha clínica vinculada

### Requirement: Búsqueda y filtrado de pacientes
El sistema SHALL permitir listar y buscar pacientes filtrando por DNI, por número de teléfono o por término de búsqueda general sobre nombre, DNI y teléfono, restringiendo siempre los resultados al `tenant_id` del usuario autenticado.

#### Scenario: Búsqueda exacta por DNI
- **WHEN** el usuario consulta `GET /api/pacientes?dni=12345678`
- **THEN** el sistema devuelve una lista con el paciente que coincida exactamente con ese DNI dentro del consultorio

#### Scenario: Búsqueda por teléfono
- **WHEN** el usuario consulta `GET /api/pacientes?telefono=1122334455`
- **THEN** el sistema devuelve los pacientes cuyo teléfono coincida con el parámetro dentro del consultorio

#### Scenario: Aislamiento estricto de pacientes entre consultorios
- **WHEN** un usuario consulta o busca pacientes en `/api/pacientes`
- **THEN** el sistema devuelve únicamente pacientes pertenecientes a su propio `tenant_id`, nunca de otros consultorios

### Requirement: Consentimiento de WhatsApp (RN-CO-01) y baja STOP
El sistema SHALL almacenar el consentimiento de WhatsApp del paciente (`optin_wa`), estableciéndolo en `false` por defecto, bloqueando todo mensaje automático si no hay opt-in activo y cortando los envíos de forma inmediata si se procesa una baja (STOP).

#### Scenario: Bloqueo de mensaje automático sin opt-in
- **WHEN** se intenta despachar un mensaje automático a un paciente con `optin_wa = false`
- **THEN** el sistema bloquea el envío y registra la omisión de acuerdo con la regla RN-CO-01

#### Scenario: Actualización de opt-in a verdadero
- **WHEN** el usuario envía `PATCH /api/pacientes/:id/optin` con `optin_wa = true`
- **THEN** el sistema actualiza el estado del paciente y permite futuros envíos automáticos

#### Scenario: Baja STOP corta los envíos
- **WHEN** el paciente solicita la baja de mensajes y se procesa `PATCH /api/pacientes/:id/optin` con `optin_wa = false`
- **THEN** el sistema desactiva el consentimiento y los mensajes automáticos quedan inmediatamente bloqueados

### Requirement: Alta implícita en reserva con get_or_create por DNI
El sistema SHALL proveer la funcionalidad de `get_or_create` por DNI para el flujo de reserva pública: si el paciente con ese DNI ya existe en el consultorio, retorna el paciente existente actualizando sus datos de contacto si fueron provistos; si no existe, lo crea junto con su ficha clínica.

#### Scenario: Paciente existente en reserva pública
- **WHEN** se invoca `get_or_create` con el DNI de un paciente ya registrado en el consultorio
- **THEN** el sistema retorna la entidad del paciente existente y actualiza nombre o teléfono si difieren

#### Scenario: Paciente nuevo en reserva pública
- **WHEN** se invoca `get_or_create` con un DNI no registrado previamente en el consultorio
- **THEN** el sistema crea un nuevo paciente con su ficha clínica 1:1 y `optin_wa = false` por defecto

### Requirement: Baja lógica de pacientes (R7)
El sistema SHALL implementar la eliminación de pacientes mediante baja lógica (`activo = false`), prohibiendo el borrado físico (hard delete) para resguardar la trazabilidad clínica y legal.

#### Scenario: Borrado lógico de paciente
- **WHEN** un usuario autorizado ejecuta `DELETE /api/pacientes/:id`
- **THEN** el sistema establece `activo = false`, registra la acción en la tabla de auditoría y no elimina la fila física de la base de datos

### Requirement: Control de acceso RBAC sobre pacientes
El sistema SHALL restringir las operaciones sobre `/api/pacientes` según la matriz RBAC: los roles Dueño y Recepción tienen permisos CRUD completos, mientras que el rol Odontólogo posee permiso exclusivo de solo lectura.

#### Scenario: Odontólogo consulta pacientes
- **WHEN** un usuario con rol odontólogo ejecuta `GET /api/pacientes` o `GET /api/pacientes/:id`
- **THEN** el sistema permite la consulta con código HTTP 200

#### Scenario: Odontólogo intenta crear o modificar paciente
- **WHEN** un usuario con rol odontólogo intenta ejecutar `POST`, `PATCH` o `DELETE` sobre `/api/pacientes`
- **THEN** el sistema rechaza la solicitud con código HTTP 403 Prohibido
