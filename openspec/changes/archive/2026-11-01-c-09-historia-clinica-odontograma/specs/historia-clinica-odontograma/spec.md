# historia-clinica-odontograma Specification

## Purpose
Garantizar el registro clínico odontológico inmutable (ficha clínica/anamnesis, evoluciones append-only con enmienda aditiva, odontograma FDI por eventos y adjuntos) y la exigencia de consentimiento informado firmado previo al inicio de la atención en prestaciones invasivas (`RN-CL-01..03`, `R7`, `R9`).

## ADDED Requirements

### Requirement: Inmutabilidad de historia clínica y edición exclusiva por rol clínico
El sistema MUST restringir la edición de `FichaClinica` y la creación de `Evolucion` a roles clínicos (`ODONTOLOGO`, `DUENO`), dejando a `RECEPCION` solo lectura (`RN-CL-03`). Cada actualización de `FichaClinica` MUST generar una `Evolucion` y un registro en `Auditoria` (`RN-CL-01`, `RN-SE-01`). Las evoluciones MUST ser append-only y corregirse mediante una nueva `Evolucion` con `es_correccion_de_id` (`R7`).

#### Scenario: Edición de ficha clínica por odontólogo genera evolución y auditoría
- **GIVEN** un paciente existente con su `FichaClinica` y un usuario con rol `ODONTOLOGO`
- **WHEN** actualiza `alergias` y `antecedentes` mediante `PUT /api/pacientes/{id}/ficha`
- **THEN** el sistema actualiza la ficha, crea automáticamente una `Evolucion` fechada y registra el cambio en `Auditoria` sin exponer PHI en logs.

#### Scenario: Recepción tiene lectura pero no puede editar contenido clínico
- **GIVEN** un usuario autenticado con rol `RECEPCION`
- **WHEN** consulta `GET /api/pacientes/{id}/ficha` e intenta `PUT /api/pacientes/{id}/ficha` o `POST /api/pacientes/{id}/evoluciones`
- **THEN** la lectura responde `200 OK` y los intentos de escritura son rechazados con `403 Forbidden` (`RN-CL-03`).

### Requirement: Odontograma FDI con historial inmutable de eventos por pieza y superficie
El sistema MUST validar que cada evento del odontograma corresponda a una pieza FDI válida (permanentes `11–48` o deciduas `51–85`), una superficie válida y un tipo de evento válido. Los cambios de estado en una pieza MUST insertarse como nuevos registros `PiezaEvento` append-only sin sobrescribir ni eliminar eventos previos (`RN-CL-01`).

#### Scenario: Registro de eventos sucesivos en una pieza conserva el historial completo
- **GIVEN** un paciente con odontograma activo
- **WHEN** el odontólogo registra primero `caries` en la pieza `16` superficie `oclusal` y luego `obturacion` en la misma pieza `16` superficie `oclusal`
- **THEN** el estado actual de la pieza `16` (`oclusal`) refleja `obturacion` y el historial de la pieza conserva ambos eventos en orden cronológico.

#### Scenario: Rechazo de numeración FDI inexistente
- **GIVEN** una solicitud para registrar un evento en el odontograma
- **WHEN** se envía una pieza fuera de la nomenclatura FDI (por ejemplo `19` o `99`)
- **THEN** el sistema rechaza la solicitud con `422 Unprocessable Entity`.

### Requirement: Consentimiento informado firmado obligatorio para prestaciones invasivas
El sistema MUST emitir y registrar la firma de `Consentimiento` por vía presencial o por `token_gestion` público (`/firmar/{token}`), almacenando `texto_version`, `firma_hash` SHA-256, `firmado_por`, `firmado_at` y `canal` (`RN-CL-02`, `RN-SE-03`). Cuando un turno corresponde a una prestación `invasiva`, el sistema MUST bloquear el paso a `presente` si no existe un consentimiento firmado vigente (`RN-CL-02`).

#### Scenario: Bloqueo de transición a presente sin consentimiento firmado en prestación invasiva
- **GIVEN** un turno en estado `confirmado` cuya prestación tiene `invasiva = True` y el paciente no posee consentimiento firmado vigente
- **WHEN** recepción o el odontólogo intenta pasar el turno a estado `presente`
- **THEN** el sistema rechaza la transición con `409 Conflict` y un mensaje claro en español rioplatense indicando que falta firmar el consentimiento informado.

#### Scenario: Firma de consentimiento por token público habilita iniciar la atención
- **GIVEN** un consentimiento pendiente de firma con su `token_gestion` vigente para el turno de una prestación invasiva
- **WHEN** el paciente firma mediante `POST /firmar/{token}` y luego se solicita pasar el turno a `presente`
- **THEN** el consentimiento queda firmado con su `firma_hash` y el turno transiciona exitosamente a `presente`.
