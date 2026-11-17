# Proposal

## Why

Los routers `pacientes`, `clinica`, `caja` y `presupuestos` solo hacen `await session.flush()` en sus endpoints mutantes (o delegan en funciones `application/*` que solo flushean) y **nunca** `await session.commit()`; `deps.sesion_db` (`src/backend/app/api/deps.py:20-24`) cierra la sesión al terminar la request y SQLAlchemy revierte todo lo no confirmado. Las altas y ediciones responden `2xx` pero **no se guardan** (verificado contra PostgreSQL real: `POST /api/pacientes` → `201` con 0 filas y mismo DNI → `201` en vez de `409`). La suite no lo detecta porque `tests/conftest.py:198-201` sobreescribe `deps.sesion_db` con `_sesion()`, que cede siempre la misma sesión compartida del test: los flush se ven ahí y el commit único ocurre en el teardown del fixture (conftest:135, después de los DELETE). Las entradas de **Estado** de C-16 y C-17 en `CHANGES.md` dejan la integración E2E de pacientes/HC y de caja "sujeta al fix de commit de sesión documentado en C-19": este change es exactamente ese fix pendiente (referencia por texto, sin números de línea, para que no se desplace con cada inserción).

## What Changes

- **Commit en los 28 endpoints mutantes** de los 4 routers sin confirmación (`pacientes.py`: 4, `clinica.py`: 8, `caja.py`: 9, `presupuestos.py`: 7): `await session.commit()` después de la última escritura (flush + auditoría), siguiendo la convención dominante ya usada en `agenda.py`, `auth.py`, `comunicaciones.py`, `liquidaciones.py`, `lista_espera.py`, `reserva_publica.py`, `admin_catalogo.py`, `usuarios.py` y `webhooks_mercadopago.py`.
- **Sin cambio de contrato visible**: mismos códigos HTTP, mismos payloads, misma lógica de negocio — la única diferencia es que la escritura queda confirmada en la base (fix quirúrgico, gobernanza CRÍTICO).
- **Tests de persistencia cross-sesión (nuevos)**: cada dominio afectado gana al menos 2 casos (R11) que verifican la fila desde una sesión/`engine` **nuevo** después de la respuesta `2xx`, más casos de atomicidad (operación fallida → nada persistido; auditoría confirmada junto con su mutación), la cadena de vencimiento de seña (turno cancelado + lista de espera + auditoría), baja lógica y opt-in de pacientes, y aislamiento multi-tenant (R4: helper filtrando por `tenant_id` del token). Patrón ya probado en `tests/test_liquidaciones_api.py:741-763`.
- **Sin cambios** en `deps.sesion_db`, en la capa `application/*`, en `unit_of_work.py`, en los routers que ya commitean, en esquema/migraciones ni en frontend (ver design D1/D2). La actualización de `CHANGES.md` y el push (R12) los coordina el orquestador en una tarea aparte.

Ningún cambio es **BREAKING**.

## Capabilities

### New Capabilities
- `persistencia-sesiones`: garantía transversal de que toda escritura aceptada por la API (pacientes, historia clínica, caja, presupuestos) confirme su transacción antes del `2xx`, quedando visible para conexiones nuevas, con atomicidad todo-o-nada por operación y auditoría en la misma transacción.

### Modified Capabilities
<!-- Ninguna: los requirements existentes de pacientes, caja-senas, historia-clinica-odontograma y presupuestos-planes ya asumen persistencia; este change hace que la implementación los cumpla sin alterar su comportamiento especificado. -->

## Impact

- **Backend (afectado)**: `src/backend/app/api/routers/pacientes.py` (4 endpoints), `clinica.py` (8, incluido `router_publico_firma`), `caja.py` (9) y `presupuestos.py` (7) — solo se agregan `await session.commit()` en la rama escritora. Intactos: `deps.sesion_db`, `app/application/*`, schemas, dominio, migraciones, seeds y los 9 routers que ya confirman.
- **Tests (afectado)**: nuevo archivo de persistencia cross-sesión (patrón `tests/test_liquidaciones_api.py:741`) con ≥2 casos por comportamiento (R11); la suite existente debe seguir en verde.
- **Riesgo / dependencia**: bloquea la firma E2E de C-16 y C-17 (secciones de **Estado** de sus entradas en `CHANGES.md` y `openspec/changes/archive/2026-11-16-c-17-frontend-caja-os-admin/proposal.md:34`); al cerrarlo quedan desbloqueadas las escrituras de pacientes/HC/caja/presupuestos antes de la demo.
- **Datos y privacidad**: sin PHI en logs, tests ni artefactos (R9); fixtures siempre sintéticas (R13).
- **Sin dependencias nuevas, sin migraciones y sin cambios de API.**

## Consultas al PO

- **Idempotencia de reintentos del cliente en POSTs mutantes (sin regla en la KB)**: doble click o reintento del cliente tras un timeout en un `POST` mutante. Antes del fix era inocuo (el reintento no persistía nada); con el commit habilitado crea filas reales (p. ej. movimiento de caja duplicado). La knowledge-base no tiene regla de idempotencia/`Idempotency-Key` para estos endpoints → **queda como pregunta abierta para el PO**, fuera del alcance de este fix (no se inventa una regla acá). Referencia: `knowledge-base/10_preguntas_abiertas.md` es el destino natural cuando el PO la responda.
