# Spec Delta

## Purpose

Provee el catálogo clínico-administrativo multi-tenant (sillones/boxes, prestaciones con duración/precio/seña/invasividad, coberturas de obras sociales por vigencia y políticas operativas del consultorio) que todo turno, presupuesto y liquidación referencia.

## ADDED Requirements

### Requirement: Administración de sillones (boxes) por sucursal y consultorio

El sistema SHALL permitir al rol Dueño crear, actualizar y desactivar (baja lógica) sillones dentro de su consultorio (`tenant_id` del token), y SHALL permitir a los roles Dueño, Recepción y Odontólogo listarlos. El nombre del sillón SHALL ser único por `(tenant_id, sucursal, nombre)`, con `sucursal = "central"` por defecto.

#### Scenario: Alta y listado de sillón en el consultorio del token
- **WHEN** un usuario con rol `dueno` crea el sillón `"Box 2"` sin especificar sucursal y luego cualquier rol interno (`dueno`, `recepcion`, `odontologo`) consulta `GET /api/admin/sillones`
- **THEN** el sillón se persiste con `sucursal = "central"` y `activo = true` bajo el `tenant_id` del token, y aparece en el listado de ese consultorio sin incluir sillones de otros tenants

#### Scenario: Nombre de sillón duplicado en la misma sucursal y consultorio
- **WHEN** se intenta crear o renombrar un sillón con un `(nombre, sucursal)` que ya existe en el mismo consultorio
- **THEN** la API responde 409 con un mensaje accionable en rioplatense y no duplica el registro

#### Scenario: Mismo nombre de sillón en otra sucursal o en otro consultorio
- **WHEN** se crea un sillón con el mismo nombre en otra sucursal del mismo consultorio o en otro consultorio distinto
- **THEN** la operación tiene éxito con 201

#### Scenario: Baja lógica de sillón (nunca hard delete)
- **WHEN** un usuario con rol `dueno` ejecuta `DELETE /api/admin/sillones/:id` sobre un sillón de su consultorio
- **THEN** el sillón permanece en la base de datos con `activo = false` y se registra el cambio en `auditoria`

### Requirement: Catálogo de prestaciones con reglas de duración, seña e invasividad

El sistema SHALL gestionar prestaciones por consultorio con `nombre` único por tenant, `duracion_min > 0`, `precio_particular >= 0`, `requiere_sena` (booleano), `monto_sena` y `invasiva` (booleano, default `false`). Si `requiere_sena = true`, el sistema SHALL exigir `monto_sena > 0`; si `requiere_sena = false`, `monto_sena` SHALL normalizarse a `null` (o `0` no exigible).

#### Scenario: Alta válida de prestación con seña e invasiva
- **WHEN** un usuario con rol `dueno` crea una prestación con `duracion_min = 60`, `precio_particular = 45000`, `requiere_sena = true`, `monto_sena = 15000` e `invasiva = true`
- **THEN** la API responde 201 con la prestación persistida bajo el `tenant_id` del token y registra el alta en `auditoria`

#### Scenario: Rechazo de prestación con duración no positiva
- **WHEN** se intenta crear o actualizar una prestación con `duracion_min <= 0`
- **THEN** la API rechaza la solicitud con 422 y un mensaje en rioplatense indicando que la duración debe ser mayor a cero

#### Scenario: Rechazo de prestación que exige seña sin monto válido
- **WHEN** se intenta crear o actualizar una prestación con `requiere_sena = true` y `monto_sena` nulo o `<= 0`
- **THEN** la API rechaza la solicitud con 422 y un mensaje en rioplatense explicando que debe informarse un monto de seña mayor a cero

### Requirement: Coberturas de obras sociales por prestación y vigencia

El sistema SHALL registrar coberturas de obra social (`CoberturaOS`) vinculadas a una prestación del mismo consultorio, con `obra_social`, `arancel >= 0`, `copago >= 0`, `vigencia_desde`, `vigencia_hasta` (opcional, `>= vigencia_desde`) y `activa`. El listado SHALL permitir filtrar coberturas vigentes a una fecha dada (por defecto o parámetro `vigente_en`) y por obra social o prestación.

#### Scenario: Alta de cobertura para una prestación del consultorio
- **WHEN** un usuario con rol `dueno` crea una cobertura para `obra_social = "OSDE 210"` sobre una prestación del mismo consultorio con `arancel = 18000`, `copago = 2000` y `vigencia_desde <= vigencia_hasta`
- **THEN** la API responde 201 y la cobertura queda disponible para las consultas del consultorio

#### Scenario: Rechazo de cobertura con rango de vigencia invertido o prestación ajena
- **WHEN** se envía `vigencia_hasta < vigencia_desde` o un `prestacion_id` que no pertenece al consultorio del token
- **THEN** la API rechaza la solicitud (422 para rango inválido, 404 para prestación inexistente en el consultorio) sin tocar datos de otros tenants

#### Scenario: Filtro de coberturas vigentes por fecha
- **WHEN** existen en el consultorio una cobertura vigente hoy y otra vencida el mes pasado, y se consulta `GET /api/admin/coberturas?vigente_en=<fecha_actual>`
- **THEN** la respuesta devuelve únicamente la cobertura cuyo rango `[vigencia_desde, vigencia_hasta]` incluye la fecha consultada y tiene `activa = true`

### Requirement: Políticas operativas del consultorio

El sistema SHALL permitir consultar (`GET /api/admin/tenant/politicas`) y actualizar parcialmente (`PATCH /api/admin/tenant/politicas`) las políticas operativas del consultorio del token (`anticipacion_min_dias`, `sena_default_pct`, `cancelacion_horas`), validando rangos válidos y registrando el antes y después en `auditoria`.

#### Scenario: Actualización parcial de políticas por el Dueño
- **WHEN** el usuario `dueno` envía `PATCH /api/admin/tenant/politicas` con `{"cancelacion_horas": 48}`
- **THEN** la política `cancelacion_horas` se actualiza a `48` conservando las demás claves existentes, y se inserta una fila en `auditoria` con `antes` y `despues`

#### Scenario: Valores fuera de rango en políticas rechazados
- **WHEN** se intenta configurar un porcentaje de seña fuera de `0..100` o horas/días negativos
- **THEN** la API responde 422 sin modificar las políticas del consultorio

### Requirement: Control de acceso por rol y aislamiento multi-tenant en catálogo

Toda operación sobre `/api/admin/sillones`, `/api/admin/prestaciones`, `/api/admin/coberturas` y `/api/admin/tenant/politicas` SHALL evaluarse contra el recurso `CONFIGURACION` de la matriz RBAC (`dueno`: CRUD; `recepcion` y `odontologo`: solo lectura `GET`) y SHALL operar exclusivamente sobre el `tenant_id` del token.

#### Scenario: Recepción y Odontólogo leen catálogo pero no pueden modificarlo
- **WHEN** un usuario con rol `recepcion` u `odontologo` realiza `GET` sobre sillones, prestaciones, coberturas o políticas y luego intenta `POST`, `PATCH` o `DELETE`
- **THEN** todas las lecturas responden 200 y todas las escrituras responden 403 con mensaje rioplatense sin modificar ningún dato

#### Scenario: Aislamiento entre consultorios y rechazo de `tenant_id` en el body
- **WHEN** un usuario del consultorio A intenta leer o modificar un ítem de catálogo del consultorio B, o envía `tenant_id` en el body de creación/edición
- **THEN** el body con `tenant_id` se rechaza con 422 (`extra='forbid'`) y el acceso a un ID del consultorio B devuelve 404 sin filtrar su existencia

### Requirement: Seed idempotente del catálogo base del consultorio piloto

El seed inicial SHALL poblar de forma idempotente en el consultorio piloto el sillón `"Box 1"` (sucursal `"central"`) y las 5 prestaciones base (`Limpieza` 30 min, `Consulta` 20 min, `Arreglo` 45 min, `Endodoncia` 60 min, `Extracción` 45 min) con precios ficticios y flags de seña e invasividad coherentes con las reglas del dominio.

#### Scenario: Ejecución repetida del seed del catálogo
- **WHEN** se ejecuta `ejecutar_seed` dos veces seguidas sobre la misma base de datos
- **THEN** el consultorio piloto queda con exactamente 1 sillón `"Box 1"` y las 5 prestaciones base activas, sin duplicar filas
