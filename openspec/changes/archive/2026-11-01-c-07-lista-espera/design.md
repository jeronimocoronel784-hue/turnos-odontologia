# Design: C-07 Lista de Espera y Oferta de Huecos (`c-07-lista-espera`)

## UI Mockups
Decision: no (no UI)

## Context
Con `C-06` (`agenda-turnos`) operativo, los turnos cancelados o reprogramados liberan huecos `[inicio, fin)` para un `(profesional_id, sillon_id)` determinado. `C-07` implementa el modelo y el motor de `ListaEspera` (Flujo 6) desacoplado del transporte efectivo de WhatsApp/SMTP (que se incorpora en `C-08`), pero dejando lista toda la máquina de estados, la clave de idempotencia por hueco/entrada (`RN-LE-02`), la rotación por vencimiento de ventana (`RN-LE-01`) y la colocación atómica en agenda por token opaco (`RN-LE-03`).

## Decisions

### D1. Modelo `ListaEspera` con estado de oferta embebido e historial de idempotencia
- **Decisión**: La tabla `lista_espera` almacena tanto los datos permanentes de la solicitud (`paciente_id`, `prestacion_id`, `profesional_id` nullable, `prioridad`, `canal_aviso`, `estado`, `turno_colocado_id`) como los metadatos de la oferta en curso (`hueco_inicio`, `hueco_fin`, `hueco_profesional_id`, `hueco_sillon_id`, `aviso_vence_at`, `ultimo_idempotency_key`) y la lista JSONB `avisos_keys` con todas las claves `idempotency_key` ya emitidas para esa entrada.
- **Por qué**: Cuando la ventana `aviso_vence_at` de la primera entrada expira sin respuesta, la entrada vuelve a `activa` para futuros huecos distintos, pero NO debe volver a ser seleccionada para el mismo hueco que dejó vencer (`RN-LE-02`). Guardar la clave `le:{entrada_id}:{prof_id}:{sillon_id}:{inicio_iso}` en `avisos_keys` y en `ultimo_idempotency_key` (con constraint único `(tenant_id, ultimo_idempotency_key)`) resuelve tanto la rotación limpia como la idempotencia en base de datos sin requerir una tabla extra fuera del modelo canónico `04_modelo_de_datos.md`.

### D2. Enganche automático al liberar un turno en Agenda
- **Decisión**: Cuando `cambiar_estado_turno` pasa un turno a `cancelado` o `ausente`, o cuando `reprogramar_turno` libera el horario del turno original, se invoca `ofrecer_hueco_lista_espera(...)` para el rango `[inicio, fin)`, `profesional_id`, `sillon_id` y `prestacion_id` liberados. Además se expone `POST /api/lista-espera/ofrecer-hueco` para disparar manualmente o desde un worker la rotación de ofertas vencidas.
- **Por qué**: Satisface el disparador del Flujo 6 ("cancelación o no-show que libera slot") en tiempo real y permite testear y operar la rotación de ventanas vencidas de forma determinística.

### D3. Prevención de doble reserva al aceptar oferta (`RN-LE-03` + `RN-AG-01`)
- **Decisión**: `aceptar_oferta_lista_espera` delega la creación del turno en `crear_turno(...)` de `app.application.agenda`. Si el hueco fue ocupado entre el aviso y la aceptación (o si dos entradas aceptan simultáneamente el mismo slot), `verificar_disponibilidad` lanza `ConflictoDisponibilidad` (`409 Conflict` con `slots_alternativos`).
- **Por qué**: Reutiliza exactamente la misma barrera transaccional anti-solapamiento de `C-06` y garantiza que la segunda aceptación reciba alternativas reales (`Flujo 6 — Casos de error`).

### D4. Reutilización de `TokenGestion` con `recurso="lista_espera"`
- **Decisión**: Al crearse una entrada en `ListaEspera` (por recepción o por `/reservar/{slug}/lista-espera`), se emite un `TokenGestion` opaco SHA-256 con `recurso="lista_espera"` y `recurso_id=str(entrada.id)`. Si la entrada recibe una oferta cuyo `aviso_vence_at` supera el vencimiento del token o requiere un token fresco, se garantiza un token activo para que el paciente gestione su entrada en `/lista-espera/{token}`.
- **Por qué**: Mantiene un único mecanismo criptográfico de tokens públicos en todo el backend (`RN-SE-03`).
