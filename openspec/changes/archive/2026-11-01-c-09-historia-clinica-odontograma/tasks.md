# Tasks: `c-09-historia-clinica-odontograma`

- [x] **1.1 Modelos de dominio clínico y migración reversible `008_historia_clinica_odontograma`** (TDD)
  - Crear `src/backend/app/domain/clinica.py` con `Evolucion`, `Odontograma`, `PiezaEvento`, `SuperficieDental`, `TipoEventoPieza`, `AdjuntoClinico`, `TipoAdjunto`, `Consentimiento`, `CanalFirmaConsentimiento` y validador `es_pieza_fdi_valida`.
  - Crear migración `src/backend/alembic/versions/008_historia_clinica_odontograma.py` (`evolucion`, `odontograma`, `pieza_evento`, `adjunto_clinico`, `consentimiento` con constraints, índices y `GRANT/REVOKE` para `turnos_app`) y registrar modelos en `alembic/env.py` y `tests/conftest.py`.
  - Verificar con `tests/test_migracion_008_clinica.py` (ciclo `upgrade head` -> `downgrade -1` -> `upgrade head`, validación FDI e inmutabilidad).

- [x] **1.2 Schemas Pydantic v2 estrictos para HC, Odontograma y Consentimientos** (TDD)
  - Crear `src/backend/app/api/schemas_clinica.py` (`extra='forbid'` en todos los inputs) para `FichaClinicaUpdate`, `FichaClinicaDetalleRead`, `EvolucionCreate`, `EvolucionRead`, `AdjuntoCreate`, `AdjuntoRead`, `PiezaEventoCreate`, `PiezaEventoRead`, `OdontogramaRead`, `ConsentimientoCreate`, `ConsentimientoFirmaInput`, `ConsentimientoRead` y `ConsentimientoPublicoRead`.
  - Verificar con `tests/test_schemas_clinica.py` (rechazo de campos extra, piezas FDI inválidas `19`/`99`, superficies y tipos de evento).

- [x] **2.1 Casos de uso clínicos, odontograma FDI y bloqueo de `presente` sin consentimiento (`RN-CL-01..03`)** (TDD)
  - Crear `src/backend/app/application/clinica.py` con actualización de `FichaClinica` que genera `Evolucion` + `Auditoria` sin PHI (`R9`), creación de evoluciones y enmiendas aditivas (`es_correccion_de_id`), registro de `AdjuntoClinico`, proyección e historial de `Odontograma`/`PiezaEvento`, y ciclo de vida de `Consentimiento` (emisión con `token_gestion`, firma presencial/token con `firma_hash` SHA-256 y revocación auditada).
  - Integrar la verificación `tiene_consentimiento_vigente` en `cambiar_estado_turno` (`src/backend/app/application/agenda.py`) cuando el turno pasa a `presente` y `prestacion.invasiva` es `True` (`RN-CL-02`).
  - Verificar con `tests/test_clinica_negocio.py`.

- [x] **3.1 Endpoints `/api/pacientes/{id}/ficha|evoluciones|adjuntos`, `/api/odontograma/*`, `/api/consentimientos/*` y `/firmar/{token}`** (TDD)
  - Crear `src/backend/app/api/routers/clinica.py` (`router` protegido por `Recurso.CLINICA` y `Recurso.CONSENTIMIENTOS`, y `router_publico_firma` para `GET/POST /firmar/{token}`) y registrarlos en `src/backend/app/main.py` y `tests/conftest.py`.
  - Verificar con `tests/test_clinica_api.py` (RBAC: recepción lee ficha pero recibe `403` al intentar editar ficha/evolución/odontograma; odontólogo edita; turno invasivo bloquea `presente` sin firma y permite `presente` tras firmar en `/firmar/{token}`).

- [x] **3.2 Calidad (`ruff`, `mypy`, suite completa) y documentación (`README.md`, `CHANGES.md`)**
  - Actualizar `README.md` y `CHANGES.md` documentando `C-09`, ejecutar `ruff check`, `ruff format --check`, `mypy` y `pytest` completo.
