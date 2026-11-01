# Proposal: `c-09-historia-clinica-odontograma`

## Why
El consultorio odontológico necesita registrar la historia clínica electrónica (HCE), las evoluciones de cada consulta, el odontograma FDI con trazabilidad por pieza/superficie y los consentimientos informados firmados antes de iniciar cualquier atención invasiva, cumpliendo con la Ley 25.326, la Ley 26.529 (HCE) y las reglas críticas de integridad (`R7`, `R9`, `RN-CL-01..03`, `RN-SE-01..03`). Sin este módulo, el profesional no puede registrar evoluciones inmutables ni el sistema puede exigir el consentimiento firmado al marcar `presente` un turno de prestación invasiva.

## What Changes
- **Dominio y Migración `008_historia_clinica_odontograma`**:
  - `Evolucion` (`evolucion`): registro append-only de cada atención o enmienda clínica (`ficha_clinica_id`, `paciente_id`, `turno_id` opcional, `profesional_id`, `nota`, `es_correccion_de_id` opcional, `created_at`). Sin borrado físico ni edición destructiva (`R7`, `RN-CL-01`).
  - `Odontograma` (`odontograma`, 1:1 por paciente) y `PiezaEvento` (`pieza_evento`, append-only): validación estricta de nomenclatura FDI adulta (`11–18`, `21–28`, `31–38`, `41–48`) y decidua (`51–55`, `61–65`, `71–75`, `81–85`), `SuperficieDental` (`oclusal`, `mesial`, `distal`, `vestibular`, `lingual`, `radicular`, `total`) y `TipoEventoPieza` (`sano`, `caries`, `obturacion`, `corona`, `endodoncia`, `implante`, `extraccion`, `ausente`, `sellador`, `provisoria`), vinculado opcionalmente a `turno_id`.
  - `AdjuntoClinico` (`adjunto_clinico`): metadatos de estudios/imágenes clínicas (`rx`, `foto`, `pdf`) vinculados a ficha/evolución/pieza sin exponer PHI en URLs (`R9`).
  - `Consentimiento` (`consentimiento`): texto versionado (`texto_version`), `firma_hash` SHA-256, `firmado_por`, `firmado_at`, `canal` (`presencial`, `token`), `revocado` (`bool`, con revocación auditada).
  - Permisos `GRANT SELECT, INSERT, UPDATE, DELETE` (y en `evolucion` y `pieza_evento` políticas append-only a nivel aplicación + auditoría) para `turnos_app` con `REVOKE` en `downgrade()`.
- **Reglas de Negocio (`RN-CL-01`, `RN-CL-02`, `RN-CL-03`, `RN-SE-01`, `RN-SE-03`)**:
  - Edición de `FichaClinica` permitida únicamente a rol clínico (`ODONTOLOGO`, `DUENO`); cada actualización de anamnesis genera automáticamente una `Evolucion` de trazabilidad y registro en `Auditoria` (`RN-CL-01`, `RN-CL-03`). `RECEPCION` tiene solo lectura (`Recurso.CLINICA`).
  - Historial inmutable en `Evolucion` y `PiezaEvento`: las correcciones crean una nueva `Evolucion` con `es_correccion_de_id` o un nuevo `PiezaEvento`; nunca se hace `UPDATE` ni `DELETE` destructivo (`R7`, `RN-CL-01`).
  - Integración en `cambiar_estado_turno` (`agenda.py`): al intentar pasar un turno a `presente`, si la `Prestacion` tiene `invasiva = True`, se verifica que exista un `Consentimiento` firmado (`firmado_at IS NOT NULL` y `revocado = False`) para ese paciente y prestación (o turno). Si no existe, se rechaza con `409 Conflict` y mensaje accionable en español rioplatense (`RN-CL-02`, `RN-GL-02`).
- **API REST y Canal Público de Firma**:
  - `GET /api/pacientes/{id}/ficha` y `PUT /api/pacientes/{id}/ficha` (`Recurso.CLINICA`).
  - `GET /api/pacientes/{id}/evoluciones`, `POST /api/pacientes/{id}/evoluciones`, `POST /api/pacientes/{id}/adjuntos` (`Recurso.CLINICA`).
  - `GET /api/odontograma/{paciente_id}`, `POST /api/odontograma/{paciente_id}/eventos` y `GET /api/odontograma/{paciente_id}/piezas/{pieza_fdi}/historial` (`Recurso.CLINICA`).
  - `GET /api/consentimientos`, `POST /api/consentimientos`, `POST /api/consentimientos/{id}/firmar`, `POST /api/consentimientos/{id}/revocar` (`Recurso.CONSENTIMIENTOS`) y ruta pública con `token_gestion` (`recurso_tipo="consentimiento"`): `GET /firmar/{token}` y `POST /firmar/{token}` (`RN-SE-03`).

## Capabilities
### New Capabilities
- `historia-clinica-odontograma`: Gestión de ficha clínica y anamnesis, evoluciones append-only con enmienda aditiva, odontograma FDI inmutable por eventos, adjuntos clínicos y consentimientos informados firmables presencialmente o por token público con bloqueo de ingreso a `presente` en prestaciones invasivas sin firma.

### Modified Capabilities
- `agenda-turnos`: `cambiar_estado_turno` hacia `presente` valida consentimiento firmado vigente cuando la prestación es `invasiva` (`RN-CL-02`).

## Impact
- **Governance**: `CRITICO` (datos clínicos protegidos por Ley 25.326 / Ley HCE, inmutabilidad append-only `R7` y privacidad `R9`).
- **Dependencias**: `C-05` (`pacientes` y `ficha_clinica` inicial) y `C-06` (`agenda-turnos`). Desbloquea `C-10` (`presupuestos-planes`) y `C-16` (`pwa-agenda-hc-admin`).
