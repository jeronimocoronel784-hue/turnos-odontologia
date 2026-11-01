# Design: `c-09-historia-clinica-odontograma`

## UI Mockups
Decision: no (no UI — este change implementa dominio, migración, lógica clínica y endpoints backend; la interfaz clínica PWA corresponde a C-16).

## Context
En `C-05` se creó la tabla inicial `ficha_clinica` (relación 1:1 con `paciente`). `C-09` completa el núcleo clínico de la Épica 3 (`US-020`, `US-021`, `US-023`):
1. Edición clínica de `FichaClinica` e historial append-only de evoluciones (`Evolucion`) con soporte de enmiendas aditivas (`es_correccion_de_id`) y adjuntos (`AdjuntoClinico`).
2. `Odontograma` (cabecera 1:1 por paciente) + `PiezaEvento` append-only con nomenclatura FDI validada y cálculo del estado vigente por pieza/superficie a partir de la secuencia de eventos.
3. `Consentimiento` informado con firma presencial o por `token_gestion` público (`/firmar/{token}`) y bloqueo en `cambiar_estado_turno` (`agenda.py`) al pasar a `presente` cuando `prestacion.invasiva == True` y no hay consentimiento firmado activo (`RN-CL-02`).

## Decisions

### D1. Inmutabilidad append-only en `Evolucion` y `PiezaEvento` (`R7`, `RN-CL-01`)
- Ningún endpoint ni servicio ofrece `DELETE` ni `UPDATE` sobre `evolucion` ni `pieza_evento`.
- Para corregir una evolución previa se crea una nueva fila en `evolucion` con `es_correccion_de_id` apuntando a la evolución original.
- Cada `PUT /api/pacientes/{id}/ficha` compara los campos modificados y genera automáticamente una fila en `evolucion` (describiendo qué secciones de la anamnesis fueron actualizadas sin volcar PHI en logs) más un registro en `auditoria`.

### D2. Nomenclatura FDI y proyección del Odontograma (`RN-CL-01`)
- Se validan las 32 piezas permanentes (`11..18`, `21..28`, `31..38`, `41..48`) y las 20 piezas deciduas (`51..55`, `61..65`, `71..75`, `81..85`).
- El odontograma cabecera (`odontograma`) se crea automáticamente (lazy o al consultar/registrar el primer evento del paciente, con `UniqueConstraint("tenant_id", "paciente_id")`).
- El estado actual de cada pieza y superficie se proyecta ordenando los `PiezaEvento` por `(created_at ASC, id ASC)`, mientras que `GET /api/odontograma/{paciente_id}/piezas/{pieza_fdi}/historial` devuelve la lista cronológica íntegra de eventos.

### D3. Consentimiento informado con `firma_hash` SHA-256 y guardia en `presente` (`RN-CL-02`, `RN-SE-03`)
- `Consentimiento` almacena `texto_version`, `firma_hash` (SHA-256 sobre `tenant_id|paciente_id|prestacion_id|texto_version|firmado_por|firmado_at_iso|firma_datos`), `firmado_por`, `firmado_at`, `canal` (`presencial` o `token`) y `revocado` (`bool`).
- Al crear un consentimiento pendiente se emite un `TokenGestion` (`recurso_tipo="consentimiento"`, `recurso_id=consentimiento.id`) para que el paciente pueda consultarlo y firmarlo en `/firmar/{token}` sin login (`RN-SE-03`).
- En `cambiar_estado_turno` (`src/backend/app/application/agenda.py`), antes de aplicar `nuevo_estado == EstadoTurno.PRESENTE`, si `prestacion.invasiva` es `True`, se consulta `tiene_consentimiento_vigente(session, tenant_id=..., paciente_id=turno.paciente_id, prestacion_id=turno.prestacion_id, turno_id=turno.id)`. Si devuelve `False`, se lanza `Conflicto` (`409`) con mensaje claro en español rioplatense.

### D4. Privacidad y Auditoría (`R9`, `RN-SE-01`)
- Los registros de `Auditoria` y logs estructurados jamás incluyen el texto libre de `nota`, `antecedentes`, `alergias`, `medicacion`, `observacion` ni `firma_datos`; solo registran IDs, códigos de pieza FDI, tipo de evento, versión de consentimiento y hashes (`R9`).
