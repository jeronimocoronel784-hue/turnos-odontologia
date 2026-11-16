# Spec Delta

## Purpose

Proporciona el shell autenticado de la PWA interna del consultorio: inicio y cierre de sesión del staff, restauración de la sesión sin persistir credenciales en el navegador, navegación acotada por rol y protección de las rutas internas, para que recepción, odontólogo y dueño operen el sistema desde el mismo frontend público de C-15.

## ADDED Requirements

### Requirement: Inicio de sesión del staff

El sistema SHALL autenticar al personal del consultorio contra la API (`POST /api/auth/login`), conservar el access token **solo en memoria** y redirigir a la agenda al completar el login.

#### Scenario: Credenciales válidas
- **WHEN** un usuario ingresa email y contraseña correctos y confirma el login
- **THEN** el sistema envía `POST /api/auth/login`, guarda el access token en memoria, muestra nombre y rol del usuario y lo redirige a la agenda interna.

#### Scenario: Credenciales inválidas
- **WHEN** la API responde `401` al login
- **THEN** el sistema muestra un mensaje genérico en rioplatense ("el email o la contraseña no son correctos") sin revelar si el email existe y mantiene el formulario con los datos cargados salvo la contraseña.

#### Scenario: Demasiados intentos
- **WHEN** la API responde `429` por rate limit de login
- **THEN** el sistema informa que se superaron los intentos permitidos y que hay que esperar antes de reintentar, sin reintentar automáticamente.

#### Scenario: Datos incompletos
- **WHEN** el usuario envía el formulario con email o contraseña vacíos o con formato inválido
- **THEN** el sistema muestra la validación local y no llama a la API.

#### Scenario: Servicio no disponible
- **WHEN** la API responde `503` o la red falla durante el login
- **THEN** el sistema muestra que el servicio no está disponible en este momento y permite reintentar sin perder el email ingresado.

### Requirement: Restauración de sesión y renovación del access token

El sistema SHALL restaurar la sesión al recargar la aplicación usando el refresh token en cookie `HttpOnly` (`POST /api/auth/refresh`), y SHALL renovar el access token una sola vez cuando la API responde `401` en un request autenticado.

#### Scenario: Recarga con sesión vigente
- **WHEN** el usuario recarga una ruta interna y la cookie de refresh sigue vigente
- **THEN** el sistema llama a `POST /api/auth/refresh` con credenciales incluidas y, si responde `200`, mantiene al usuario en la ruta solicitada sin pedirle la contraseña de nuevo.

#### Scenario: Recarga sin sesión válida
- **WHEN** el usuario abre una ruta interna sin cookie de refresh o el refresh responde `401`
- **THEN** el sistema lo redirige al login y, después de autenticarse, lo devuelve a la ruta interna que había pedido.

#### Scenario: Expiración durante el uso
- **WHEN** un request autenticado recibe `401` porque el access token venció
- **THEN** el sistema intenta un único refresh y reintenta el request original; si el refresh falla, descarta la sesión y vuelve al login con el aviso de que la sesión venció.

#### Scenario: Varios requests vencidos a la vez
- **WHEN** dos o más consultas reciben `401` en simultáneo
- **THEN** el sistema ejecuta un solo refresh y reintenta todas las consultas afectadas con el token renovado, sin bucles de refresh.

#### Scenario: Credenciales fuera del almacenamiento del navegador
- **WHEN** el usuario navega e interactúa con la aplicación interna
- **THEN** el sistema no escribe el access token, el refresh token ni datos de pacientes en `localStorage` ni en `sessionStorage`, y la sesión sobrevive a una recarga únicamente por la cookie de refresh.

### Requirement: Cierre de sesión

El sistema SHALL cerrar la sesión del staff descartando el access token en memoria y limpiando los datos de consultas en caché.

#### Scenario: Logout exitoso
- **WHEN** el usuario elige cerrar sesión
- **THEN** el sistema llama a `POST /api/auth/logout`, limpia el access token y la caché de consultas, y redirige al login.

#### Scenario: Logout sin conexión
- **WHEN** el pedido de logout falla por red o `5xx`
- **THEN** el sistema descarta igualmente la sesión local y redirige al login, informando que la sesión se cerró en este dispositivo.

### Requirement: Control de acceso por rol en la interfaz

El sistema SHALL habilitar rutas, secciones y acciones según el rol del usuario autenticado, con la misma matriz de permisos que aplica el backend; el backend SHALL seguir siendo la autoridad final.

#### Scenario: Recepción en la historia clínica
- **WHEN** un usuario con rol `recepcion` abre la ficha clínica de un paciente
- **THEN** el sistema le permite leer la ficha y las evoluciones, pero no muestra acciones para editarlas ni registrar eventos de odontograma.

#### Scenario: Recepción gestiona la firma del consentimiento
- **WHEN** un usuario con rol `recepcion` atiende una prestación invasiva que no tiene consentimiento vigente
- **THEN** el sistema le permite emitir, firmar en el acto o revocar el consentimiento (la matriz de §03 le da CRUD sobre consentimientos) y luego reintentar el inicio de la atención, sin habilitarle la edición de la ficha ni del odontograma.

#### Scenario: Odontólogo en pacientes
- **WHEN** un usuario con rol `odontologo` abre la sección de pacientes
- **THEN** el sistema le permite buscar y leer fichas, pero no muestra las acciones de alta, edición, baja ni cambio de opt-in.

#### Scenario: Dueño en la operación diaria
- **WHEN** un usuario con rol `dueno` usa la aplicación interna
- **THEN** el sistema muestra todas las acciones del alcance de este change (agenda, pacientes, clínica, presupuestos y comunicaciones).

#### Scenario: Acceso directo a una sección sin permiso
- **WHEN** un usuario escribe en la barra de direcciones una ruta interna para la que su rol no tiene permiso
- **THEN** el sistema muestra una pantalla de acceso denegado en rioplatense con un enlace de vuelta a la agenda, sin ejecutar consultas de esa sección.

#### Scenario: Rol ausente o desconocido
- **WHEN** la identidad devuelta por la API no trae un rol conocido o viene vacía
- **THEN** el sistema deniega por defecto el acceso a todas las secciones internas (fail-closed) y ofrece cerrar sesión.

#### Scenario: El backend rechaza una acción que la UI mostró
- **WHEN** una acción visible para el usuario obtiene `403` de la API
- **THEN** el sistema muestra el mensaje de permiso denegado del backend y refresca la identidad, sin reintentar la acción.

### Requirement: Navegación y layout interno

El sistema SHALL ofrecer una navegación interna coherente que exponga únicamente las secciones habilitadas para el rol y mantenga la identidad y el cierre de sesión accesibles.

#### Scenario: Menú filtrado por rol
- **WHEN** se carga el layout interno
- **THEN** el menú muestra solo las secciones sobre las que el rol tiene al menos permiso de lectura (agenda, pacientes, clínica y comunicaciones), ocultando las demás.

#### Scenario: Identidad y salida siempre visibles
- **WHEN** el usuario navega entre secciones internas
- **THEN** el layout mantiene visibles el nombre y el rol del usuario y la acción de cerrar sesión.

#### Scenario: Uso en pantalla chica
- **WHEN** la aplicación interna se abre en un ancho de pantalla móvil
- **THEN** la navegación se colapsa en un menú accesible por botón y el contenido no genera scroll horizontal.

#### Scenario: Ruta interna inexistente
- **WHEN** el usuario entra a una ruta interna que no existe
- **THEN** el sistema muestra un estado "no encontramos esa página" con un enlace a la agenda, sin afectar las rutas públicas de C-15.

### Requirement: Tratamiento uniforme de errores de la API

El sistema SHALL presentar los errores de la API de forma uniforme y en español rioplatense, sin exponer detalles técnicos ni datos sensibles. Todo rechazo SHALL indicar qué pasó, por qué y cómo seguir (RN-GL-02), ofreciendo la acción concreta cuando exista.

#### Scenario: Recurso inexistente
- **WHEN** una consulta responde `404`
- **THEN** el sistema muestra el mensaje de "no encontramos" correspondiente y ofrece volver o reintentar según la pantalla.

#### Scenario: Recurso de otro consultorio
- **WHEN** una consulta pide un paciente, turno o presupuesto que no pertenece al consultorio del token
- **THEN** el sistema muestra el "no encontramos" del backend y no revela la existencia ni datos del recurso ajeno (R4, RN-SE-02).

#### Scenario: Error del servidor o de red
- **WHEN** una consulta responde `5xx` o falla por red
- **THEN** el sistema muestra un mensaje genérico con la opción de reintentar, sin mostrar stack traces, cuerpos crudos ni identificadores internos.

#### Scenario: Error con datos sensibles
- **WHEN** la API devuelve un error que incluye texto libre
- **THEN** el sistema muestra el mensaje tal como lo devolvió el backend y no lo registra junto con datos del paciente en consola ni en almacenamiento del navegador.
