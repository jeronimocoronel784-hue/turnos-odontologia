# Spec Delta

## Purpose

Proporciona las pantallas internas del consultorio sobre la PWA existente: agenda multi-profesional con turnos, estados, bloqueos y sobreturnos; gestión de pacientes; historia clínica con odontograma FDI, adjuntos, consentimientos y presupuestos del plan; y log de comunicaciones con reenvío y plantillas, respetando la matriz de permisos del backend y sin persistir datos clínicos en el navegador.

## ADDED Requirements

### Requirement: Vista de agenda por día y semana

El sistema SHALL mostrar los turnos y bloqueos de un rango de fechas consultando `GET /api/agenda`, con filtros por profesional, sillón y estado, y con la duración real de cada turno.

#### Scenario: Carga de la vista diaria
- **WHEN** el usuario abre la agenda en una fecha
- **THEN** el sistema consulta `/api/agenda` con el rango del día y muestra cada turno en la columna de su profesional y sillón, con altura proporcional a su duración.

#### Scenario: Agenda del odontólogo acotada a sus turnos
- **WHEN** un usuario con rol `odontologo` abre la agenda
- **THEN** la vista arranca filtrada por su propio `profesional_id` y, si consulta turnos de otro profesional, los ve en solo lectura (sin acciones de estado ni reprogramación), porque §03 le da lectura y actualización solo sobre sus turnos.

#### Scenario: Cambio a vista semanal
- **WHEN** el usuario cambia a la vista de semana o navega a la semana anterior o siguiente
- **THEN** el sistema consulta el nuevo rango conservando los filtros de profesional, sillón y estado ya elegidos.

#### Scenario: Filtros combinados
- **WHEN** el usuario filtra por un profesional y un sillón a la vez
- **THEN** la agenda muestra solo los turnos y bloqueos que cumplen ambos filtros y permite limpiarlos de una vez.

#### Scenario: Rango inválido
- **WHEN** el rango de fechas pedido termina antes de empezar
- **THEN** el sistema no dispara la consulta y muestra un aviso de fechas inválidas.

#### Scenario: Agenda sin turnos
- **WHEN** el rango consultado no tiene turnos ni bloqueos
- **THEN** el sistema muestra un estado vacío en rioplatense con la acción de crear un turno.

### Requirement: Estados, bloqueos y sobreturnos en la agenda

El sistema SHALL distinguir visualmente el estado de cada turno, los bloqueos no reservables y los sobreturnos.

#### Scenario: Estados diferenciados
- **WHEN** la agenda muestra turnos en estados `pendiente`, `confirmado`, `presente`, `ausente`, `cancelado` y `finalizado`
- **THEN** cada estado se identifica con una etiqueta textual y un color distinto, sin depender solo del color.

#### Scenario: Bloqueo no reservable
- **WHEN** el usuario intenta crear un turno sobre una franja ocupada por un bloqueo
- **THEN** el sistema lo advierte antes de enviar el alta y no permite confirmar sobre esa franja.

#### Scenario: Sobreturno marcado
- **WHEN** un turno tiene `sobreturno` activo
- **THEN** la agenda lo muestra con una marca explícita que lo distingue de un turno normal, incluso si comparte franja horaria.

#### Scenario: Seña pendiente visible
- **WHEN** un turno corresponde a una prestación que requiere seña y todavía no está cobrada
- **THEN** la agenda lo señala como "seña pendiente" y el detalle muestra el estado de la seña, sin calcular montos en el cliente (R8, RN-PA-01).

#### Scenario: Turno cancelado
- **WHEN** un turno está `cancelado` y tiene motivo de cancelación
- **THEN** la agenda lo muestra atenuado con el motivo visible al abrir su detalle.

### Requirement: Alta de turno desde la agenda

El sistema SHALL permitir dar de alta un turno interno eligiendo paciente, profesional, sillón, prestación e inicio, y SHALL reflejarlo en la agenda al confirmarse.

#### Scenario: Alta exitosa
- **WHEN** el usuario completa paciente, profesional, sillón, prestación e inicio y confirma
- **THEN** el sistema envía `POST /api/turnos`, recibe `201` y muestra el nuevo turno en la agenda sin recargar la página.

#### Scenario: Solapamiento
- **WHEN** el alta devuelve `409` porque la franja ya está ocupada
- **THEN** el sistema muestra el mensaje del backend y no agrega el turno a la vista, dejando el formulario abierto para elegir otro horario.

#### Scenario: Paciente inexistente
- **WHEN** el paciente buscado no existe al armar el turno
- **THEN** el sistema ofrece darlo de alta en el momento y, al volver, conserva profesional, sillón, prestación e inicio elegidos.

#### Scenario: Duración sugerida por prestación
- **WHEN** el usuario elige una prestación
- **THEN** el sistema propone el horario de fin a partir de la duración informada por el catálogo; si el usuario lo ajusta, lo marca como override manual y le pide un motivo que viaja en las observaciones del turno (RN-AG-02).

#### Scenario: Alta con sobreturno explícito
- **WHEN** el usuario necesita crear un sobreturno
- **THEN** debe marcar explícitamente `sobreturno = true` y escribir un motivo; sin motivo el sistema no envía el alta y nunca crea un sobreturno en silencio (RN-AG-04).

#### Scenario: Datos obligatorios faltantes
- **WHEN** el usuario intenta confirmar el alta sin paciente, profesional, sillón o inicio
- **THEN** el sistema muestra la validación local y no llama a la API.

### Requirement: Cambio de estado y cancelación de turnos

El sistema SHALL permitir cambiar el estado de un turno (`PATCH /api/turnos/{id}/estado`) dentro del grafo cerrado de la KB (`pendiente → confirmado → presente → finalizado`; desde `pendiente` o `confirmado` hacia `cancelado`, `ausente` o `reprogramado`), SHALL exigir motivo al cancelar y SHALL informar el bloqueo cuando falte un requisito previo.

#### Scenario: Confirmar turno
- **WHEN** el usuario confirma un turno `pendiente`
- **THEN** el sistema envía el cambio, recibe `200` y muestra el turno como `confirmado`.

#### Scenario: Marcar presente o finalizado
- **WHEN** el usuario marca un turno como `presente` o `finalizado`
- **THEN** el sistema envía el cambio, recibe `200` y actualiza la etiqueta del turno en la agenda.

#### Scenario: Marcar ausente
- **WHEN** el usuario marca `ausente` un turno `pendiente` o `confirmado` porque el paciente no se presentó
- **THEN** el sistema envía el cambio, recibe `200` y, si el turno tenía seña cobrada, muestra el aviso de que la seña se retiene según la política (RN-PA-04).

#### Scenario: Cancelación con motivo
- **WHEN** el usuario cancela un turno sin escribir un motivo
- **THEN** el sistema no envía el cambio y le pide el motivo; con motivo completo envía la cancelación y muestra el estado `cancelado`.

#### Scenario: Seña pendiente bloquea la confirmación
- **WHEN** el usuario intenta confirmar un turno cuya prestación requiere seña y `sena_cobrada` es falso
- **THEN** el sistema muestra el bloqueo del backend (`409`, RN-PA-01) con el mensaje de que hay que cobrar la seña antes, y el turno queda en su estado anterior.

#### Scenario: Prestación invasiva sin consentimiento
- **WHEN** el usuario intenta marcar `presente` un turno de una prestación invasiva que no tiene consentimiento vigente
- **THEN** el sistema muestra el bloqueo informado por el backend y ofrece la acción de firmar el consentimiento antes de reintentar.

#### Scenario: Acciones no ofrecidas
- **WHEN** el turno está `finalizado` (estado terminal) o la transición pedida no pertenece al grafo
- **THEN** el sistema no ofrece esa acción en la interfaz; si el backend la rechaza, muestra el motivo y no cambia el estado mostrado.

#### Scenario: Transición rechazada
- **WHEN** la API rechaza el cambio de estado (`409` o `422`)
- **THEN** el sistema muestra el motivo y revierte el cambio optimista, dejando el turno en el estado que confirma el servidor.

### Requirement: Reprogramación en un clic con historial

El sistema SHALL permitir reprogramar un turno eligiendo un nuevo horario y SHALL exponer la cadena de reprogramaciones.

#### Scenario: Reprogramación exitosa
- **WHEN** el usuario elige un nuevo inicio para un turno existente y confirma
- **THEN** el sistema envía `POST /api/turnos/{id}/reprogramar`, recibe `201` y muestra el turno nuevo en la agenda, mientras el original pasa a `reprogramado` con su historial intacto y el nuevo queda vinculado por `turno_origen_id` (RN-AG-06).

#### Scenario: Reprogramación rechazada
- **WHEN** la reprogramación devuelve `409` por solapamiento o fuera de la política
- **THEN** el sistema muestra el mensaje y conserva el horario elegido para que el usuario pruebe otro.

#### Scenario: Historial de reprogramaciones
- **WHEN** el usuario abre el detalle de un turno reprogramado
- **THEN** el sistema muestra el turno de origen y permite recorrer la cadena de reprogramaciones hasta el turno actual.

### Requirement: Actualización de la agenda ante confirmaciones de WhatsApp

El sistema SHALL reflejar en la agenda los cambios de estado producidos por el webhook de WhatsApp sin que el usuario recargue la página.

#### Scenario: Confirmación recibida
- **WHEN** un turno pasa a `confirmado` por una confirmación del paciente mientras la agenda está abierta
- **THEN** la agenda vuelve a consultar el rango visible en un intervalo acotado y muestra el nuevo estado.

#### Scenario: Pestaña en segundo plano
- **WHEN** la ventana de la aplicación no está visible
- **THEN** el sistema suspende el refresco periódico y lo reanuda al volver a la pestaña.

#### Scenario: Fallo del refresco periódico
- **WHEN** una consulta de refresco falla por red
- **THEN** el sistema mantiene la agenda visible con los últimos datos y muestra un aviso discreto, sin vaciar la vista.

### Requirement: Búsqueda y alta de pacientes

El sistema SHALL permitir buscar pacientes por nombre, DNI o teléfono y darlos de alta con su ficha clínica asociada.

#### Scenario: Búsqueda con resultados
- **WHEN** el usuario escribe un término de búsqueda
- **THEN** el sistema consulta `/api/pacientes` con ese término y lista nombre, DNI y teléfono de los pacientes del consultorio que coinciden.

#### Scenario: Búsqueda sin resultados
- **WHEN** la búsqueda no devuelve pacientes
- **THEN** el sistema muestra un estado vacío que ofrece dar de alta un paciente con los datos ya escritos.

#### Scenario: DNI duplicado
- **WHEN** el alta devuelve `409` porque ya existe un paciente con ese DNI en el consultorio
- **THEN** el sistema muestra el mensaje y ofrece abrir la ficha del paciente existente.

#### Scenario: Alta exitosa
- **WHEN** el alta de paciente devuelve `201`
- **THEN** el sistema abre el detalle del paciente creado y, al volver a la búsqueda, el paciente aparece en los resultados.

#### Scenario: Término de búsqueda fuera de la barra de direcciones
- **WHEN** el usuario busca por DNI o teléfono
- **THEN** el término no se escribe en la barra de direcciones ni en el historial del navegador.

### Requirement: Detalle, edición y opt-in del paciente

El sistema SHALL mostrar la ficha de contacto del paciente y permitir editarla, cambiar el opt-in de WhatsApp y darlo de baja de forma lógica.

#### Scenario: Edición de datos de contacto
- **WHEN** el usuario guarda cambios de nombre, teléfono, email, obra social o fecha de nacimiento
- **THEN** el sistema envía el `PATCH`, recibe `200` y muestra los datos actualizados.

#### Scenario: Cambio de opt-in
- **WHEN** el usuario activa o desactiva el opt-in de WhatsApp
- **THEN** el sistema envía `PATCH /api/pacientes/{id}/optin` y muestra el estado resultante, indicando que sin opt-in no se envían mensajes al paciente.

#### Scenario: Baja lógica
- **WHEN** el usuario da de baja un paciente
- **THEN** el sistema envía la baja, muestra al paciente como inactivo y explica que sus datos y su historia clínica se conservan.

#### Scenario: Pacientes inactivos
- **WHEN** el usuario busca pacientes sin pedir inactivos
- **THEN** el sistema excluye a los inactivos de los resultados y permite incluirlos con un filtro explícito.

### Requirement: Ficha clínica y evoluciones inmutables

El sistema SHALL mostrar la ficha clínica del paciente y permitir al rol clínico registrar anamnesis y evoluciones, sin opciones de edición ni borrado de evoluciones.

#### Scenario: Lectura de la ficha
- **WHEN** el usuario abre la ficha clínica de un paciente
- **THEN** el sistema muestra antecedentes, alergias, medicación, hábitos y las evoluciones existentes en orden cronológico.

#### Scenario: Guardar anamnesis
- **WHEN** un usuario con permiso clínico guarda la ficha
- **THEN** el sistema envía la actualización, recibe `200` y muestra los datos guardados.

#### Scenario: Nueva evolución
- **WHEN** un usuario con permiso clínico registra una evolución con nota
- **THEN** el sistema envía el alta, recibe `201` y agrega la evolución fechada al final del listado.

#### Scenario: Corrección aditiva
- **WHEN** el usuario corrige una evolución
- **THEN** el sistema crea una evolución nueva que referencia a la original y la muestra identificada como corrección, sin modificar la nota anterior.

#### Scenario: Sin acciones de edición
- **WHEN** el usuario ve una evolución registrada
- **THEN** el sistema no ofrece acciones de edición ni de borrado sobre ella.

#### Scenario: Nota vacía
- **WHEN** el usuario intenta guardar una evolución sin nota
- **THEN** el sistema muestra la validación local y no llama a la API.

### Requirement: Odontograma FDI interactivo e historial por pieza

El sistema SHALL renderizar el odontograma con la notación FDI y permitir registrar eventos por pieza y superficie, consultando el historial de cada pieza.

#### Scenario: Render del odontograma
- **WHEN** el usuario abre el odontograma de un paciente
- **THEN** el sistema consulta `GET /api/odontograma/{paciente_id}` y muestra las piezas FDI agrupadas por cuadrante con el estado actual de cada una.

#### Scenario: Selección de pieza y superficie
- **WHEN** el usuario selecciona una pieza
- **THEN** el sistema muestra las superficies disponibles y los eventos ya registrados para esa pieza.

#### Scenario: Registro de evento
- **WHEN** el usuario elige una superficie y un evento y confirma
- **THEN** el sistema envía el alta del evento, recibe `201`, repinta la pieza y agrega el evento al historial.

#### Scenario: Pieza fuera de la notación FDI
- **WHEN** el usuario intenta registrar un evento sobre una pieza que no pertenece a la notación FDI
- **THEN** el sistema no lo permite y muestra el error de validación.

#### Scenario: Historial de la pieza
- **WHEN** el usuario consulta el historial de una pieza
- **THEN** el sistema muestra los eventos en orden cronológico con fecha, evento, superficie y profesional que los registró.

### Requirement: Adjuntos clínicos

El sistema SHALL permitir registrar los metadatos de un estudio o imagen clínica asociado al paciente y listarlos en su historia clínica.

#### Scenario: Registro de metadatos de un adjunto
- **WHEN** el usuario registra tipo, nombre de archivo, tipo MIME, tamaño y clave de almacenamiento
- **THEN** el sistema envía el alta, recibe `201` y agrega el adjunto al listado del paciente.

#### Scenario: Adjunto asociado a una evolución o evento
- **WHEN** el usuario asocia el adjunto a una evolución o a un evento de odontograma
- **THEN** el sistema muestra esa relación en el listado del paciente.

#### Scenario: Metadatos incompletos
- **WHEN** falta el nombre de archivo, el tipo o un tamaño válido
- **THEN** el sistema muestra la validación local y no llama a la API.

#### Scenario: Sin archivos en el navegador
- **WHEN** el usuario registra un adjunto
- **THEN** el sistema no copia el contenido del archivo ni sus metadatos a `localStorage` o `sessionStorage`.

### Requirement: Consentimientos informados

El sistema SHALL permitir consultar, crear, firmar en el acto y revocar consentimientos, mostrando siempre la versión del texto firmado.

#### Scenario: Consentimiento faltante antes de la atención
- **WHEN** el usuario intenta iniciar la atención de una prestación invasiva sin consentimiento vigente
- **THEN** el sistema muestra el bloqueo y ofrece crear y firmar el consentimiento en el acto.

#### Scenario: Alta de consentimiento
- **WHEN** el usuario crea un consentimiento para un paciente y una prestación
- **THEN** el sistema envía el alta, recibe `201` y muestra el texto con su versión y estado sin firmar.

#### Scenario: Firma en el acto
- **WHEN** el usuario firma un consentimiento
- **THEN** el sistema envía la firma, recibe `200` y muestra quién firmó, la fecha y el hash de la firma.

#### Scenario: Revocación
- **WHEN** el usuario revoca un consentimiento sin indicar motivo
- **THEN** el sistema no envía la revocación y pide el motivo; con motivo completo muestra el consentimiento como revocado.

#### Scenario: Revocación vuelve a bloquear la atención
- **WHEN** un consentimiento fue revocado y el usuario intenta marcar `presente` el turno de esa prestación invasiva
- **THEN** el sistema vuelve a mostrar el bloqueo del backend, porque una firma revocada no cuenta como consentimiento vigente (RN-CL-02).

#### Scenario: Operación rechazada por el backend
- **WHEN** la API rechaza firmar o revocar un consentimiento ya procesado
- **THEN** el sistema muestra el mensaje del backend y recarga el estado real del consentimiento.

### Requirement: Presupuestos del plan del paciente

El sistema SHALL mostrar los presupuestos del paciente con sus ítems y totales calculados por el servidor, permitir crear presupuestos, avanzar su estado y vincularle turnos del plan.

#### Scenario: Ver presupuestos del paciente
- **WHEN** el usuario abre el plan de un paciente
- **THEN** el sistema lista los presupuestos con estado, ítems, cobertura y montos tal como los devuelve el servidor.

#### Scenario: Presupuesto sin cobertura
- **WHEN** un presupuesto no tiene cobertura de obra social vigente
- **THEN** el sistema muestra el total a cargo informado por el servidor (equivalente al total) sin recalcularlo en el cliente (RN-OS-01, R8).

#### Scenario: Alta de presupuesto
- **WHEN** el usuario crea un presupuesto eligiendo prestaciones, piezas y cantidades
- **THEN** el sistema envía el alta, recibe `201` y muestra los totales calculados por el servidor sin recalcularlos en el cliente.

#### Scenario: Avance del presupuesto
- **WHEN** el usuario presenta, acepta, rechaza o finaliza un presupuesto
- **THEN** el sistema envía la transición, recibe `200` y muestra el nuevo estado.

#### Scenario: Aceptar un presupuesto con prestación invasiva sin consentimiento
- **WHEN** el usuario intenta aceptar un presupuesto que incluye una prestación invasiva sin consentimiento vigente
- **THEN** el sistema muestra el rechazo del backend (`409`, RN-CL-04) y ofrece firmar el consentimiento antes de reintentar.

#### Scenario: Vínculo de turnos al plan
- **WHEN** el usuario vincula un turno al presupuesto
- **THEN** el sistema envía el vínculo, recibe la respuesta y muestra el turno asociado y el estado del presupuesto que devuelve el servidor (al vincular el primero pasa a `en_curso`, RN-CL-04).

#### Scenario: Pieza inválida en un ítem
- **WHEN** el usuario indica una pieza que no pertenece a la notación FDI
- **THEN** el sistema muestra la validación local y no envía el presupuesto.

### Requirement: Log de comunicaciones y reenvío manual

El sistema SHALL mostrar los mensajes generados para un turno o paciente, su estado y permitir reenviarlos manualmente.

#### Scenario: Consulta del log
- **WHEN** el usuario abre las comunicaciones de un turno o paciente
- **THEN** el sistema consulta `/api/mensajes` y muestra canal, plantilla, versión, estado, intentos, fecha programada y cuerpo renderizado.

#### Scenario: Reenvío manual
- **WHEN** el usuario reenvía un mensaje
- **THEN** el sistema envía el reenvío, recibe la respuesta y agrega el nuevo mensaje en estado pendiente al log.

#### Scenario: Paciente sin opt-in
- **WHEN** el usuario intenta reenviar un mensaje a un paciente sin opt-in de WhatsApp
- **THEN** el sistema advierte que no se enviará y lo registra como omisión, sin marcar el mensaje como enviado.

#### Scenario: Error del proveedor
- **WHEN** un mensaje quedó en estado de error
- **THEN** el sistema muestra el motivo informado por el backend y habilita el reenvío.

#### Scenario: Sin mensajes
- **WHEN** el turno o paciente no tiene mensajes
- **THEN** el sistema muestra un estado vacío que explica que solo se envían mensajes con opt-in activo.

### Requirement: Plantillas de mensajes versionadas

El sistema SHALL mostrar las plantillas del consultorio y permitir al dueño crear nuevas versiones, respetando que los mensajes enviados conservan la versión con la que se generaron.

#### Scenario: Recepción en plantillas
- **WHEN** un usuario con rol `recepcion` abre las plantillas
- **THEN** el sistema las muestra en modo lectura y no ofrece acciones de alta o edición.

#### Scenario: Dueño crea una nueva versión
- **WHEN** un usuario con rol `dueno` guarda un cambio sobre una plantilla existente
- **THEN** el sistema envía el alta de una nueva versión y muestra la versión incrementada junto a las anteriores.

#### Scenario: Versión conservada en el log
- **WHEN** el usuario consulta un mensaje generado antes de una nueva versión de la plantilla
- **THEN** el log sigue mostrando la versión con la que ese mensaje se generó.

### Requirement: Política de cancelación visible

El sistema SHALL mostrar la política de cancelación del consultorio (con el default de 24 h cuando la configuración no la cambie, RN-AG-05) y SHALL advertir al usuario cuando una cancelación o reprogramación cae fuera del plazo, informando además la consecuencia sobre la seña.

#### Scenario: Política disponible
- **WHEN** el usuario abre la agenda o el detalle de un turno
- **THEN** el sistema muestra la anticipación mínima, las horas de cancelación configuradas y, si corresponde, el valor por defecto de 24 h.

#### Scenario: Cancelación fuera del plazo
- **WHEN** el usuario cancela o reprograma un turno con menos anticipación que la configurada
- **THEN** el sistema advierte que la acción queda fuera del plazo, pide confirmación explícita y, si el turno tenía seña cobrada, informa que la seña se retiene y se aplica a gastos (RN-PA-04) antes de enviar.

#### Scenario: Resultado informado por el backend
- **WHEN** la cancelación o reprogramación fuera de término se confirma
- **THEN** el sistema muestra el estado y la situación de la seña que devuelve el backend, sin decidir por su cuenta si corresponde devolución, retención o cargo.

#### Scenario: Política no disponible
- **WHEN** la consulta de políticas falla
- **THEN** el sistema muestra un aviso genérico y deja que el backend decida, sin bloquear la operación por ese error.

### Requirement: Privacidad de los datos clínicos en el cliente

El sistema SHALL evitar la persistencia de datos clínicos y personales en el navegador y SHALL limitar la exposición de datos sensibles en la interfaz y en los registros del cliente.

#### Scenario: Datos clínicos fuera del almacenamiento
- **WHEN** el usuario navega por fichas, odontograma, evoluciones, presupuestos y mensajes
- **THEN** el sistema no escribe historia clínica, odontograma, DNI, teléfono ni cuerpos de mensajes en `localStorage` o `sessionStorage`.

#### Scenario: Limpieza al cerrar sesión
- **WHEN** el usuario cierra sesión o la sesión vence
- **THEN** el sistema descarta la caché de consultas clínicas en memoria y no deja datos de pacientes visibles para el próximo usuario del dispositivo.

#### Scenario: Identificadores en la interfaz
- **WHEN** la interfaz necesita mostrar referencias a pacientes, profesionales o prestaciones
- **THEN** muestra nombres legibles y nunca UUIDs crudos como texto principal.
