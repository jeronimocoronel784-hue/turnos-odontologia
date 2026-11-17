# persistencia-sesiones Specification

## Purpose

Garantiza que toda escritura aceptada por la API confirme su transacción en la base de datos antes de responder, de modo que las altas, ediciones y bajas de pacientes, historia clínica, caja y presupuestos sean visibles para cualquier sesión o request posterior, con atomicidad todo-o-nada y auditoría en la misma transacción.

## Requirements

### Requirement: Confirmación de la transacción antes del 2xx
El sistema SHALL confirmar (`commit`) la transacción de toda operación mutante antes de devolver una respuesta `2xx`, de modo que la escritura quede persistida y sea visible desde una sesión de base de datos distinta a la de la request.

#### Scenario: Alta de paciente visible desde una sesión nueva
- **WHEN** se crea un paciente con `POST /api/pacientes` y la API responde `201 Created`
- **THEN** una sesión de base de datos abierta después de la respuesta consulta el paciente recién creado junto con su ficha clínica 1:1

#### Scenario: Edición de paciente visible desde una sesión nueva
- **WHEN** se actualiza un paciente con `PATCH /api/pacientes/{id}` y la API responde `200 OK`
- **THEN** una sesión de base de datos distinta a la de la request lee los campos actualizados del paciente

#### Scenario: Baja lógica de paciente visible desde una sesión nueva
- **WHEN** se da de baja un paciente con `DELETE /api/pacientes/{id}` y la API responde `200 OK`
- **THEN** una sesión de base de datos distinta a la de la request consulta la misma fila del paciente con `activo=false` (baja lógica, sin hard delete — R7)

#### Scenario: Opt-in de mensajes visible desde una sesión nueva
- **WHEN** se cambia el consentimiento de WhatsApp con `PATCH /api/pacientes/{id}/optin` a `true` y luego a `false`, cada uno respondiendo `200 OK`
- **THEN** una sesión de base de datos distinta a la de la request lee `optin_wa` con el último valor enviado (compuerta de mensajes automáticos — RN-CO-01)

#### Scenario: Escritura de caja visible desde una sesión nueva
- **WHEN** se registra un movimiento con `POST /api/caja/movimientos` y la API responde `201 Created`
- **THEN** una sesión de base de datos distinta a la de la request consulta el movimiento con su estado y monto confirmados

#### Scenario: Cobro de seña visible desde una sesión nueva
- **WHEN** se cobra una seña con `POST /api/senas/{id}/cobrar` y la API responde `200 OK`
- **THEN** una sesión de base de datos distinta a la de la request consulta la seña en estado `cobrada` junto con el movimiento de ingreso asociado

#### Scenario: Vencimiento de seña con su cadena completa visible desde una sesión nueva
- **WHEN** se vence una seña impaga con `POST /api/senas/{id}/vencer` y la API responde `2xx`
- **THEN** una sesión de base de datos distinta a la de la request observa la seña en estado `vencida`, el turno asociado en `cancelado` (RN-AG-07), la entrada de lista de espera actualizada por la oferta del slot liberado (RN-LE-01) y la fila de auditoría de la operación, todo junto (RN-PA-01)

#### Scenario: Escritura de historia clínica visible desde una sesión nueva
- **WHEN** se registra una evolución, un evento de odontograma o un consentimiento con `201 Created`
- **THEN** una sesión de base de datos distinta a la de la request consulta el registro clínico persistido

### Requirement: Atomicidad todo-o-nada de la operación mutante
El sistema SHALL aplicar cada operación mutante de forma atómica: si la respuesta es `2xx` todos los cambios de esa operación (entidad principal, registros relacionados y auditoría) quedan confirmados; si la operación termina en error `4xx`/`5xx`, ninguno de sus cambios queda persistido.

#### Scenario: Operación fallida no deja escrituras parciales
- **WHEN** una operación mutante falla después de haber escrito datos intermedios en la sesión (por ejemplo, rechazo por DNI duplicado o validación de negocio)
- **THEN** una sesión de base de datos distinta a la de la request no observa ningún cambio de esa operación

#### Scenario: Respuesta de éxito confirma todos los registros relacionados
- **WHEN** una operación mutante que escribe una entidad principal, registros relacionados y su auditoría responde `2xx`
- **THEN** una sesión de base de datos distinta a la de la request observa todos los registros de esa operación, nunca un subconjunto parcial

### Requirement: Auditoría en la misma transacción que la mutación
El sistema SHALL persistir el registro de auditoría de una operación mutante en la misma transacción que la mutación, de modo que no exista auditoría sin su hecho correspondiente ni hecho sin su auditoría cuando ambos responden `2xx`.

#### Scenario: Auditoría de la alta confirmada junto con el hecho
- **WHEN** se crea una entidad auditada (paciente, movimiento de caja, evolución, presupuesto) y la API responde `2xx`
- **THEN** una sesión de base de datos distinta a la de la request consulta tanto la entidad como su entrada en `auditoria`

#### Scenario: Operación fallida sin entrada de auditoría huérfana
- **WHEN** una operación auditada termina en error antes de confirmarse
- **THEN** una sesión de base de datos distinta a la de la request no observa la entrada de auditoría de esa operación

### Requirement: Coherencia de lectura posterior tras un 2xx
El sistema SHALL garantizar que una lectura posterior (misma request de lectura posterior o una request nueva) devuelva lo escrito por una operación mutante confirmada, sin depender de la sesión de la request original.

#### Scenario: Lectura posterior devuelve lo escrito
- **WHEN** una operación mutante responde `2xx` y luego se ejecuta `GET` sobre el mismo recurso desde una request nueva
- **THEN** el `GET` devuelve el recurso con los datos de la operación confirmada

#### Scenario: Recurso inexistente no aparece tras una operación fallida
- **WHEN** una operación de **alta** termina en error `4xx` y luego se ejecuta `GET` sobre el recurso pretendido desde una request nueva
- **THEN** el `GET` responde `404 Not Found`, sin rastro de la operación fallida

#### Scenario: Recurso existente conserva el estado anterior tras una edición fallida
- **WHEN** una operación de **edición** sobre un recurso existente termina en error `4xx` y luego se ejecuta `GET` sobre ese recurso desde una request nueva
- **THEN** el `GET` devuelve el recurso con su estado anterior a la edición fallida, sin rastro del intento

### Requirement: Aislamiento multi-tenant de las escrituras persistidas
El sistema SHALL filtrar toda escritura y toda verificación de persistencia por el `tenant_id` del token autenticado, de modo que lo creado con el token de un tenant no sea observable —desde ninguna sesión nueva— con el token de otro tenant (R4).

#### Scenario: Escritura de un tenant invisible para otro tenant
- **WHEN** se crea una entidad con el token del tenant A y la API responde `2xx`, y luego una sesión de base de datos distinta la consulta con el `tenant_id` del tenant B
- **THEN** la consulta no devuelve la entidad creada por el tenant A

#### Scenario: Escritura del propio tenant visible con el token del propio tenant
- **WHEN** se crea una entidad con el token del tenant A y la API responde `2xx`, y luego una sesión de base de datos distinta la consulta con el `tenant_id` del tenant A
- **THEN** la consulta devuelve la entidad creada, filtrada por el `tenant_id` del token
