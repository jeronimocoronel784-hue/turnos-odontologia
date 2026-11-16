# Spec Delta

## Purpose

Proporciona las pantallas de administración del consultorio sobre el shell autenticado: prestaciones, sillones/sucursal, padrón de coberturas, políticas operativas, usuarios y roles, más un panel del día alimentado por datos del servidor y la capa de consistencia visual y accesibilidad que cierra el producto interno.

## ADDED Requirements

### Requirement: Prestaciones del consultorio

El sistema SHALL listar las prestaciones con su duración, precio, seña e indicador de prestación invasiva, y SHALL permitir al Dueño darlas de alta, editarlas y desactivarlas sin borrarlas.

#### Scenario: Listado de prestaciones
- **WHEN** el usuario abre la configuración de prestaciones
- **THEN** el sistema consulta `/api/prestaciones` y muestra nombre, duración, precio particular, si requiere seña con su monto, si es invasiva y si está activa.

#### Scenario: Alta de prestación
- **WHEN** el Dueño crea una prestación con nombre, duración y precio
- **THEN** el sistema envía `POST /api/prestaciones`, recibe `201` y muestra la prestación en el listado con el precio que confirmó el servidor.

#### Scenario: Seña sin monto
- **WHEN** el Dueño marca que la prestación requiere seña sin informar el monto
- **THEN** el sistema muestra la validación y no envía el alta.

#### Scenario: Precio o duración inválidos
- **WHEN** el precio es negativo o la duración no es un entero positivo
- **THEN** el sistema muestra la validación local y no llama a la API.

#### Scenario: Desactivar prestación
- **WHEN** el Dueño desactiva una prestación
- **THEN** el sistema envía la desactivación, recibe `200` y la muestra como inactiva, sin desaparecer del listado ni de los turnos ya creados.

### Requirement: Sillones y sucursal

El sistema SHALL permitir administrar los sillones del consultorio con su sucursal y su estado de actividad.

#### Scenario: Alta de sillón
- **WHEN** el Dueño crea un sillón con nombre y sucursal
- **THEN** el sistema envía `POST /api/sillones`, recibe `201` y muestra el sillón en el listado.

#### Scenario: Sucursal por defecto
- **WHEN** el Dueño crea un sillón sin indicar sucursal
- **THEN** el sistema muestra la sucursal `central` que aplica el servidor como valor por defecto.

#### Scenario: Desactivar sillón
- **WHEN** el Dueño desactiva un sillón
- **THEN** el sistema envía la desactivación, recibe `200` y lo muestra como inactivo, aclarando que deja de estar disponible para agendar.

#### Scenario: Nombre vacío
- **WHEN** el nombre del sillón está vacío
- **THEN** el sistema muestra la validación local y no llama a la API.

### Requirement: Padrón de coberturas de obra social

El sistema SHALL permitir administrar las coberturas por obra social y prestación con arancel, copago y vigencia.

#### Scenario: Alta de cobertura
- **WHEN** el Dueño crea una cobertura con obra social, prestación, arancel, copago y vigencia
- **THEN** el sistema envía `POST /api/coberturas`, recibe `201` y la muestra en el padrón con el estado de vigencia calculado por el servidor.

#### Scenario: Vigencia invertida
- **WHEN** la fecha de vigencia hasta es anterior a la de desde
- **THEN** el sistema muestra la validación local y no envía la cobertura.

#### Scenario: Edición de arancel
- **WHEN** el Dueño actualiza el arancel o el copago de una cobertura existente
- **THEN** el sistema envía el `PATCH`, recibe `200` y muestra los valores nuevos, aclarando que no modifican liquidaciones ni cobros ya generados.

#### Scenario: Desactivar cobertura
- **WHEN** el Dueño desactiva una cobertura
- **THEN** el sistema la muestra como inactiva y deja de ofrecerla al consultar cobertura para agendar.

### Requirement: Políticas operativas del consultorio

El sistema SHALL mostrar y permitir editar las políticas del consultorio (anticipación mínima, porcentaje de seña por defecto y horas de cancelación) con los rangos que valida el servidor.

#### Scenario: Ver políticas
- **WHEN** el Dueño abre la configuración de políticas
- **THEN** el sistema consulta `GET /api/tenant/politicas` y muestra anticipación mínima, porcentaje de seña por defecto y horas de cancelación.

#### Scenario: Guardar políticas
- **WHEN** el Dueño modifica las horas de cancelación y guarda
- **THEN** el sistema envía el `PATCH`, recibe `200` y muestra los valores confirmados por el servidor.

#### Scenario: Porcentaje fuera de rango
- **WHEN** el porcentaje de seña por defecto queda fuera de 0 a 100
- **THEN** el sistema muestra la validación local y no envía el cambio.

#### Scenario: Valores no modificados
- **WHEN** el Dueño guarda sin cambiar ningún campo
- **THEN** el sistema no envía un `PATCH` vacío y avisa que no hay cambios para guardar.

### Requirement: Usuarios y roles del consultorio

El sistema SHALL listar los usuarios del consultorio, permitir al Dueño darlos de alta y cambiarles el rol, sin exponer nunca credenciales ni hashes.

#### Scenario: Listado de usuarios
- **WHEN** el Dueño abre la sección de usuarios
- **THEN** el sistema consulta `/api/usuarios` y muestra nombre, email, rol y matrícula, sin ningún campo de contraseña ni hash.

#### Scenario: Alta de usuario
- **WHEN** el Dueño crea un usuario con email, nombre, rol y contraseña
- **THEN** el sistema envía el alta, recibe `201` y muestra el usuario en el listado, sin volver a mostrar la contraseña ingresada.

#### Scenario: Odontólogo sin matrícula
- **WHEN** el Dueño crea un usuario con rol `odontologo` sin matrícula
- **THEN** el sistema muestra la validación (local y del backend) y no crea el usuario.

#### Scenario: Cambio de rol
- **WHEN** el Dueño cambia el rol de un usuario
- **THEN** el sistema envía `PATCH /api/usuarios/{id}/rol`, recibe `200` y muestra el rol nuevo, aclarando que impacta en los accesos de ese usuario.

#### Scenario: Email duplicado
- **WHEN** el alta devuelve `409` porque el email ya existe en el consultorio
- **THEN** el sistema muestra el mensaje del backend y no agrega el usuario al listado.

### Requirement: Panel del consultorio con datos del servidor

El sistema SHALL mostrar un panel del día con el estado del cierre de caja, las liquidaciones abiertas, las señas pendientes o vencidas y los turnos del día, usando exclusivamente valores agregados o listados que devuelve el servidor.

#### Scenario: Panel del día
- **WHEN** el dueño o la recepción abren el panel
- **THEN** el sistema muestra el cierre de la fecha con `total_sistema`, `total_contado` y `diferencia`, las liquidaciones en borrador y presentadas con sus totales, las señas pendientes o vencidas y los turnos del día por estado.

#### Scenario: Caja sin abrir
- **WHEN** todavía no hay cierre de caja para la fecha
- **THEN** el sistema lo indica y ofrece la acción de abrir el cierre, sin mostrar totales en cero como si la caja estuviera cuadrada.

#### Scenario: Sin liquidaciones abiertas
- **WHEN** no hay liquidaciones en borrador ni presentadas
- **THEN** el sistema muestra el estado vacío correspondiente con el enlace a liquidaciones.

#### Scenario: Refresco del panel
- **WHEN** el panel queda abierto con la pestaña visible
- **THEN** el sistema vuelve a consultar sus datos en un intervalo acotado y se detiene cuando la pestaña pasa a segundo plano.

#### Scenario: Montos del panel
- **WHEN** el panel muestra cualquier importe
- **THEN** ese importe proviene de un campo del servidor y el cliente no suma ni resta dinero para mostrarlo (R8).

### Requirement: Consistencia de estados en la aplicación interna

El sistema SHALL presentar en todas las pantallas internas los estados de carga, vacío y error con el mismo patrón y mensajes accionables en español rioplatense.

#### Scenario: Estado de carga
- **WHEN** una pantalla espera datos del servidor
- **THEN** el sistema muestra un indicador de carga consistente con el resto de las pantallas y no un salto de layout.

#### Scenario: Estado vacío
- **WHEN** una consulta no devuelve resultados
- **THEN** el sistema muestra un estado vacío con la explicación de por qué no hay datos y la acción concreta para empezar.

#### Scenario: Error accionable
- **WHEN** una consulta falla por permiso, recurso inexistente o error del servidor
- **THEN** el sistema indica qué pasó, por qué y cómo seguir, ofreciendo reintentar o volver, sin mostrar stack traces ni identificadores internos (RN-GL-02).

#### Scenario: Error de red parcial
- **WHEN** una consulta falla por red mientras otras pantallas ya cargaron
- **THEN** el sistema conserva lo ya visible, marca solo la sección afectada y permite reintentar esa consulta.

### Requirement: Accesibilidad y uso en pantallas chicas

El sistema SHALL ser operable con teclado y en pantallas de 360 px de ancho, sin depender únicamente del color para transmitir información.

#### Scenario: Ancho móvil
- **WHEN** una pantalla interna de C-17 se abre en un ancho de 360 px
- **THEN** el contenido se adapta sin scroll horizontal y las acciones principales quedan alcanzables.

#### Scenario: Navegación por teclado
- **WHEN** el usuario recorre la pantalla con la tecla Tab
- **THEN** el foco es visible en cada control interactivo y el orden de foco sigue el orden visual del formulario.

#### Scenario: Estados sin color
- **WHEN** se muestran estados de cierre, liquidación o seña
- **THEN** cada estado incluye su etiqueta textual además del color.

#### Scenario: Campos obligatorios
- **WHEN** un formulario tiene campos obligatorios
- **THEN** cada campo tiene su etiqueta asociada y el error se anuncia junto al campo, no solo como color de borde.

### Requirement: Permisos de administración

El sistema SHALL habilitar las secciones de administración según el rol, dejando la lectura abierta a recepción y odontólogo y la escritura reservada al Dueño.

#### Scenario: Recepción en configuración
- **WHEN** un usuario con rol `recepcion` abre prestaciones, sillones, coberturas o políticas
- **THEN** el sistema se las muestra en solo lectura, sin acciones de alta, edición ni desactivación.

#### Scenario: Odontólogo en usuarios
- **WHEN** un usuario con rol `odontologo` abre la sección de usuarios
- **THEN** el sistema le muestra el listado en solo lectura y no ofrece alta ni cambio de rol.

#### Scenario: Dueño en administración
- **WHEN** un usuario con rol `dueno` abre cualquier sección de administración
- **THEN** el sistema le habilita las acciones de escritura que permite la matriz de §03.

#### Scenario: Escritura rechazada
- **WHEN** una acción de escritura obtiene `403` del backend
- **THEN** el sistema muestra el mensaje de permiso denegado y refresca la identidad, sin reintentar la escritura.

### Requirement: Datos sensibles en la administración

El sistema SHALL evitar la persistencia de credenciales y datos personales en el navegador y SHALL limitar la exposición de datos sensibles en las pantallas de administración.

#### Scenario: Credenciales fuera del navegador
- **WHEN** el Dueño crea un usuario o cambia su rol
- **THEN** el sistema no escribe la contraseña, el email ni el rol en `localStorage` o `sessionStorage`.

#### Scenario: Contraseña no recuperable
- **WHEN** el usuario vuelve a abrir el listado de usuarios
- **THEN** el sistema no muestra contraseñas ni hashes, solo los datos de identidad y rol que devuelve el servidor (R9).

#### Scenario: Cierre de sesión
- **WHEN** el usuario cierra sesión o la sesión vence
- **THEN** el sistema descarta la caché de usuarios, políticas y padrón, y no deja datos del consultorio visibles para el próximo usuario del dispositivo.
