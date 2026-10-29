# Spec Delta

## Purpose

Define cómo el sistema prueba quién es cada usuario interno, qué puede hacer según su rol, y cómo un paciente sin cuenta opera de forma segura mediante tokens públicos vencibles.

## ADDED Requirements

### Requirement: Login de staff interno

El sistema SHALL autenticar usuarios internos activos con email + password verificado contra hash bcrypt y SHALL emitir un access token JWT y un refresh token en la misma respuesta. Un email inexistente, password incorrecto o usuario inactivo SHALL devolver el mismo 401 genérico, sin revelar cuál de los tres falló.

#### Scenario: Credenciales válidas
- **WHEN** un usuario activo envía su email y password correctos
- **THEN** recibe 200 con access token y datos mínimos de identidad, y el refresh token viaja en cookie HttpOnly

#### Scenario: Password incorrecto o usuario inexistente
- **WHEN** se envía un password incorrecto o un email que no existe
- **THEN** la respuesta es 401 con el mismo mensaje genérico en ambos casos, sin indicar cuál falló

#### Scenario: Usuario inactivo
- **WHEN** un usuario con `activo = false` envía credenciales correctas
- **THEN** la respuesta es 401 y no se emite ningún token

#### Scenario: Email presente en más de un consultorio
- **WHEN** el email existe en dos tenants y el login no especifica `tenant_slug`
- **THEN** la respuesta es 400 pidiendo el consultorio y no se autentica en ninguno

#### Scenario: Email repetido con consultorio explícito
- **WHEN** el email existe en dos tenants y el login envía `tenant_slug`
- **THEN** se autentica únicamente contra el usuario de ese consultorio

### Requirement: Rate limiting de login

El sistema SHALL limitar los intentos de login a 5 por ventana de 60 segundos por combinación de IP y email. Al superar el límite SHALL responder 429 con un mensaje rioplatense que indique cuánto esperar, y SHALL registrar el bloqueo sin exponer el email completo en logs (R9).

#### Scenario: Sexto intento en la ventana
- **WHEN** se realizan 5 intentos de login fallidos para el mismo email desde la misma IP dentro de 60 segundos
- **THEN** el sexto intento devuelve 429 sin verificar credenciales

#### Scenario: Ventana expirada
- **WHEN** pasan más de 60 segundos desde el bloqueo
- **THEN** un nuevo intento vuelve a evaluarse normalmente

### Requirement: Rotación de refresh token con detección de reúso

Cada refresh SHALL emitir un refresh token nuevo y revocar el anterior dentro de la misma familia de sesión. El reúso de un refresh ya rotado SHALL revocar toda la familia y devolver 401, obligando a un login nuevo.

#### Scenario: Refresh normal
- **WHEN** el cliente presenta un refresh vigente y no usado
- **THEN** recibe un access token nuevo y un refresh nuevo, y el refresh presentado queda revocado

#### Scenario: Reúso de refresh rotado
- **WHEN** se presenta un refresh que ya fue rotado
- **THEN** la respuesta es 401, toda la familia de esa sesión queda revocada y el refresh vigente de esa familia deja de servir

#### Scenario: Refresh vencido o revocado por logout
- **WHEN** se presenta un refresh vencido o revocado explícitamente
- **THEN** la respuesta es 401 sin emitir tokens nuevos

### Requirement: Entrega segura del refresh token

El refresh token SHALL viajar únicamente en cookie HttpOnly con `secure` y `samesite=lax`, y SHALL ser inaccesible para JavaScript. El access token SHALL viajar en el body de la respuesta y usarse como `Authorization: Bearer`.

#### Scenario: Cookie del refresh
- **WHEN** el login o el refresh responden con éxito
- **THEN** la cookie del refresh incluye `HttpOnly`, `Secure` y `SameSite=Lax`, y el body no contiene el refresh en texto plano

### Requirement: Claims y vigencia del access token

El access token SHALL incluir los claims `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat` y `exp`, con vigencia `JWT_ACCESS_MIN`. Un token vencido, con firma inválida o con `type` distinto de access SHALL ser rechazado con 401 antes de ejecutar cualquier lógica de negocio.

#### Scenario: Token válido
- **WHEN** se llama a un endpoint interno con un access token vigente y bien firmado
- **THEN** la request se procesa con la identidad del token

#### Scenario: Token vencido o manipulado
- **WHEN** se envía un access token vencido, con firma inválida o un refresh usado como access
- **THEN** la respuesta es 401 y no se toca ningún dato

### Requirement: Identidad del usuario autenticado

El sistema SHALL exponer `GET /api/auth/me` para que un usuario autenticado consulte su identidad (id, email, nombre, roles, tenant) sin incluir hash de password ni datos clínicos.

#### Scenario: Consulta de identidad
- **WHEN** un usuario autenticado llama a `GET /api/auth/me`
- **THEN** recibe 200 con su id, email, nombre, roles y tenant, sin `password_hash`

### Requirement: Logout con revocación de sesión

`POST /api/auth/logout` SHALL revocar la sesión del refresh presentado, borrar la cookie y hacer que ese refresh deje de servir. Llamarlo sin sesión válida SHALL responder 204 sin error.

#### Scenario: Logout con sesión activa
- **WHEN** un usuario autenticado llama a `POST /api/auth/logout`
- **THEN** recibe 204, la cookie se borra y el refresh revocado ya no puede usarse

#### Scenario: Logout idempotente
- **WHEN** se llama a `POST /api/auth/logout` sin cookie o con una cookie ya revocada
- **THEN** la respuesta es 204 y no se expone ningún detalle interno

### Requirement: Autorización por matriz de roles enforced en la API

Toda operación interna SHALL validarse contra la matriz de permisos de `03_actores_y_roles.md` en el backend, no solo en la UI. Una operación no permitida SHALL devolver 403 con mensaje accionable en rioplatense, sin revelar datos del recurso.

#### Scenario: Recepción lee configuración sin poder modificarla
- **WHEN** un usuario con rol recepcion consulta la configuración del tenant y luego intenta modificarla
- **THEN** la lectura responde 200 y la modificación responde 403

#### Scenario: Recepción intenta editar clínica
- **WHEN** un usuario con rol recepcion intenta modificar una ficha clínica u odontograma
- **THEN** la API responde 403 y el dato no cambia

#### Scenario: Odontólogo intenta reabrir un cierre de caja
- **WHEN** un usuario con rol odontólogo intenta reabrir un cierre de caja
- **THEN** la API responde 403 y el cierre permanece cerrado

#### Scenario: Dueño con doble rol operativo
- **WHEN** un usuario con rol dueno ejecuta una acción administrativa y una acción clínica permitidas por la matriz
- **THEN** ambas se autorizan, porque el rol Dueño cubre CRUD administrativo y clínico

### Requirement: Tenant efectivo tomado del token

El `tenant_id` usado en toda consulta y escritura SHALL provenir del token autenticado. Un `tenant_id` enviado en body, query o path SHALL ser ignorado o rechazado, nunca usado para ampliar el alcance del usuario (R4).

#### Scenario: Cliente intenta forzar otro tenant
- **WHEN** un usuario del tenant A envía un `tenant_id` del tenant B en el body o query
- **THEN** la operación se ejecuta (o se rechaza) según el tenant del token, sin acceder jamás a datos del tenant B

### Requirement: Rechazos de autorización sin filtración

Un 403 por rol insuficiente SHALL NO revelar si el recurso existe, a quién pertenece ni datos del mismo. El mensaje SHALL explicar qué permiso falta y cómo pedirlo, sin códigos crudos (RN-GL-02).

#### Scenario: Recurso ajeno a un rol sin permiso
- **WHEN** un rol sin permiso sobre un recurso inexistente y otro existente hacen la misma llamada
- **THEN** ambas respuestas son 403 con el mismo mensaje, sin distinguir existencia ni pertenencia

### Requirement: Token público de gestión para el paciente sin login

El sistema SHALL emitir tokens públicos de gestión (`token_gestion`) con entropía suficiente para no ser adivinables, guardados hasheados en reposo, atados a un recurso y a un tenant, y con vencimiento obligatorio. La validación SHALL rechazar tokens vencidos, revocados o de otro recurso.

#### Scenario: Token vigente del recurso correcto
- **WHEN** el paciente presenta un token vigente correspondiente al recurso solicitado
- **THEN** puede ver y operar únicamente ese recurso

#### Scenario: Token vencido o revocado
- **WHEN** se presenta un token vencido o revocado
- **THEN** la respuesta es 401 con mensaje rioplatense y no se expone ningún dato del recurso

#### Scenario: Token de otro recurso o de otro tenant
- **WHEN** se usa un token válido para un recurso distinto del solicitado, o de otro tenant
- **THEN** la respuesta es 404 o 401 sin revelar datos de terceros (RN-SE-03)

#### Scenario: Token no se guarda en claro
- **WHEN** se inspecciona la base de datos
- **THEN** el valor almacenado es un hash del token y nunca el token en texto plano

### Requirement: Auditoría de eventos de autenticación

Todo login exitoso, login fallido con usuario existente, logout y revocación de familia SHALL registrarse en la tabla append-only `auditoria` con actor (cuando exista), acción y timestamp, sin PHI ni credenciales (R9, RN-SE-01).

#### Scenario: Login exitoso auditado
- **WHEN** un usuario inicia sesión correctamente
- **THEN** se inserta un registro de auditoría con la acción de login y el actor, sin password ni tokens

#### Scenario: Revocación por reúso auditada
- **WHEN** se detecta reúso de un refresh token
- **THEN** se inserta un registro de auditoría de revocación de familia asociado al usuario afectado
