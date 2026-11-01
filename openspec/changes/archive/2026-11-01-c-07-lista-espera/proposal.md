# Proposal: C-07 Lista de Espera y Oferta de Huecos (`c-07-lista-espera`)

## Why

Las cancelaciones sobre la hora y las ausencias dejan huecos vacíos en la agenda odontológica que son difíciles de rellenar manualmente por teléfono. Implementar la lista de espera automatizada (**Flujo 6**) permite ofrecer cada hueco liberado en orden estricto de prioridad y antigüedad (`RN-LE-01`), garantizando idempotencia por hueco/entrada (`RN-LE-02`) y convirtiendo la aceptación por token en un `Turno` real sin riesgo de doble reserva (`RN-LE-03`).

## What Changes

1. **Dominio y Migración (`006_lista_espera`)**:
   - Modelo `ListaEspera` (`src/backend/app/domain/lista_espera.py`) con aislamiento `tenant_id`, referencias a `Paciente`, `Prestacion`, `Usuario` (`profesional_id` opcional) y `Turno` (`turno_colocado_id` opcional), `prioridad` entera, `estado` (`activa`, `avisada`, `colocada`, `baja`), `canal_aviso` (`wa`, `email`), datos del hueco ofrecido (`hueco_inicio`, `hueco_fin`, `hueco_profesional_id`, `hueco_sillon_id`, `aviso_vence_at`), `ultimo_idempotency_key` e historial de claves avisadas (`avisos_keys` JSONB).
   - Migración reversible `006_lista_espera.py` encadenada a `005_agenda_turnos` con constraints de integridad, índice de ordenamiento `(tenant_id, estado, prioridad, created_at)` y permisos para `turnos_app`.
2. **Casos de Uso de Lista de Espera e Integración con Agenda (`src/backend/app/application/lista_espera.py`)**:
   - Alta de entrada con emisión de `TokenGestion` (`recurso="lista_espera"`).
   - Algoritmo de ofrecimiento y rotación de huecos (`ofrecer_hueco_lista_espera`): vence ofertas expiradas, selecciona la primera entrada `activa` compatible ordenada por `(prioridad ASC, created_at ASC)` que aún no haya sido avisada para ese hueco (`idempotency_key` único por entrada + hueco, `RN-LE-01`, `RN-LE-02`), y la pasa a `avisada` con ventana de respuesta configurable.
   - Enganche automático al cancelar o reprogramar un turno en `app/application/agenda.py` para ofrecer el hueco liberado al primer candidato compatible.
   - Aceptación de oferta (`aceptar_oferta_lista_espera`, `RN-LE-03`): verifica vigencia de la ventana, crea el `Turno` mediante `crear_turno` (si hubo carrera o doble aceptación simultánea, gana la primera y la segunda recibe `409 Conflict` con `slots_alternativos`), y marca la entrada `colocada`.
   - Baja voluntaria o administrativa (`dar_baja_lista_espera`): pasa a `baja` y, si tenía un hueco ofrecido activo, rota la oferta al siguiente candidato en la fila.
3. **Contratos Pydantic y Routers HTTP**:
   - Schemas estrictos (`extra="forbid"`, `R1`) en `src/backend/app/api/schemas_lista_espera.py`.
   - Router interno `src/backend/app/api/routers/lista_espera.py`: `GET /api/lista-espera`, `POST /api/lista-espera`, `GET /api/lista-espera/{id}`, `PATCH /api/lista-espera/{id}`, `POST /api/lista-espera/ofrecer-hueco` protegido por RBAC (`Recurso.LISTA_ESPERA`).
   - Endpoints públicos sin login en el mismo módulo/router público: `POST /reservar/{slug}/lista-espera`, `GET /lista-espera/{token}`, `POST /lista-espera/{token}/aceptar`, `POST /lista-espera/{token}/baja`.

## Capabilities

### New Capabilities
- `lista-espera`: Gestión de lista de espera odontológica multi-tenant, oferta ordenada e idempotente de huecos liberados, rotación por vencimiento de ventana y colocación automática en agenda por token opaco.

### Modified Capabilities
- Ninguna spec existente modifica sus requisitos normativos; `agenda-turnos` se integra invocando la oferta de hueco al liberarse un turno.

## Impact

- **Base de datos**: Nueva tabla `lista_espera` en migración `006_lista_espera`.
- **API**: Nuevas rutas internas `/api/lista-espera*` y públicas `/reservar/{slug}/lista-espera` y `/lista-espera/{token}*`.
- **Seguridad y Auditoría**: Reutiliza `TokenGestion` (`recurso="lista_espera"`) con SHA-256 (`RN-SE-03`) y registra transiciones en `auditoria` (`RN-SE-01`).
