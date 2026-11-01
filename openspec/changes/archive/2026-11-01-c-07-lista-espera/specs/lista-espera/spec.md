# Spec: Lista de Espera (`lista-espera`)

## ADDED Requirements

### Requirement: Persistencia multi-tenant y ordenamiento de lista de espera
El sistema MUST persistir cada entrada de `ListaEspera` asociada a un `tenant_id`, `paciente_id`, `prestacion_id`, `profesional_id` (opcional), `prioridad` entera (`>= 0`), `estado` (`activa`, `avisada`, `colocada`, `baja`), `canal_aviso` (`wa`, `email`) y marcas temporales. El orden de prioridad para ofrecer huecos MUST ser estrictamente por `(prioridad ASC, created_at ASC)` dentro del mismo `tenant_id` (`RN-LE-01`).

#### Scenario: Listado y selección respetan prioridad y antigüedad
- **GIVEN** tres entradas activas en el mismo consultorio: A (`prioridad=1`, creada a las 09:00), B (`prioridad=0`, creada a las 10:00) y C (`prioridad=1`, creada a las 08:30)
- **WHEN** se consulta la lista de espera o se busca candidato para un hueco compatible
- **THEN** el orden devuelto es B, luego C y finalmente A.

### Requirement: Oferta idempotente de hueco liberado y rotación por vencimiento
Al liberarse un hueco en la agenda, el sistema MUST ofrecerlo a la primera entrada `activa` compatible que no haya recibido ya un aviso para ese hueco (`idempotency_key`, `RN-LE-02`), pasándola a `avisada` con ventana `aviso_vence_at`. Si la ventana vence sin aceptación, al reevaluarse el hueco el sistema MUST devolver la entrada vencida a `activa` y ofrecer el hueco a la siguiente compatible en la fila (`RN-LE-01`).

#### Scenario: Primer candidato pasa a avisada y no recibe doble aviso por el mismo hueco
- **GIVEN** una entrada `activa` compatible con el hueco liberado `2026-11-20 10:00`
- **WHEN** se ofrece el hueco por primera vez
- **THEN** la entrada pasa a `avisada` con `ultimo_idempotency_key` único para ese hueco y entrada
- **AND** si se vuelve a ejecutar la oferta para el mismo hueco mientras está vigente o tras haber sido avisada, no se duplica el aviso para la misma entrada.

#### Scenario: Ventana vencida rota al siguiente candidato compatible
- **GIVEN** dos entradas activas E1 (mayor prioridad) y E2 (siguiente prioridad) para la misma prestación, donde E1 fue `avisada` pero su `aviso_vence_at` ya expiró
- **WHEN** se ejecuta la oferta/rotación del mismo hueco
- **THEN** E1 vuelve a estado `activa` (sin volver a ser elegida para ese mismo hueco) y E2 pasa a estado `avisada`.

### Requirement: Aceptación por token opaco y colocación en agenda sin doble reserva
El paciente con una entrada en estado `avisada` y ventana vigente MUST poder aceptar el hueco mediante `POST /lista-espera/{token}/aceptar`. Al aceptar, el sistema MUST crear el `Turno` vinculado y cambiar el estado de la entrada a `colocada` registrando `turno_colocado_id` (`RN-LE-03`). Si el hueco ya fue ocupado entre tanto (o ante doble aceptación simultánea), el sistema MUST ganar solo para la primera transacción y rechazar la segunda con `409 Conflict` y `slots_alternativos` (`RN-GL-02`).

#### Scenario: Aceptación exitosa crea turno y marca entrada colocada
- **GIVEN** una entrada en estado `avisada` con ventana vigente y su `token_gestion`
- **WHEN** el paciente envía `POST /lista-espera/{token}/aceptar`
- **THEN** el sistema responde `201 Created`, crea el `Turno` en el hueco ofrecido y la entrada queda en estado `colocada` con `turno_colocado_id` asignado.

#### Scenario: Doble aceptación o slot ya ocupado devuelve 409 con alternativas
- **GIVEN** una entrada en estado `avisada` para un hueco que acaba de ser ocupado por otro turno
- **WHEN** el paciente intenta aceptar con `POST /lista-espera/{token}/aceptar`
- **THEN** el sistema responde `409 Conflict` con mensaje rioplatense claro y la lista `slots_alternativos`.

### Requirement: Gestión pública por token y RBAC en endpoints internos
El sistema MUST permitir que un paciente se anote públicamente en `/reservar/{slug}/lista-espera` y consulte o se dé de baja en `/lista-espera/{token}` y `/lista-espera/{token}/baja` sin exponer datos de terceros (`RN-SE-03`). En los endpoints internos `/api/lista-espera*`, el sistema MUST exigir autenticación JWT, filtrar por `tenant_id` del token (`R4`) y aplicar la matriz RBAC (`Recurso.LISTA_ESPERA`: `dueno` y `recepcion` CRUD; `odontologo` solo lectura).

#### Scenario: Odontólogo puede leer la lista de espera pero recibe 403 al crear o dar de baja
- **GIVEN** un token JWT con rol `odontologo`
- **WHEN** invoca `GET /api/lista-espera` y luego `POST /api/lista-espera`
- **THEN** recibe `200 OK` en la lectura y `403 Forbidden` en la creación.
