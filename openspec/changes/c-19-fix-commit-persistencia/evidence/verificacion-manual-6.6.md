# Evidencia — 6.6 Verificación manual contra PostgreSQL real

> Change: `c-19-fix-commit-persistencia` · Fecha: 2026-11-16 · Datos 100 % sintéticos (R13); sin PHI real en logs ni en este archivo (R9).

## Contexto

- **DB desechable**: `turnos_c19_verify` en PostgreSQL 18 local (`127.0.0.1:5432`), creada para esta verificación y separada de cualquier base de desarrollo.
- **Migraciones**: `python -m alembic upgrade head` → `001_inicial` … `013_liquidacion_claim_unico` (13 migraciones, sin errores).
- **Seed**: `python -m app.infrastructure.seed` → `{'tenants': 1, 'duenos': 1, 'sillones': 1, 'prestaciones': 5}`.
- **Usuario demo**: `python -m app.scripts.usuario_demo` → `demo.piloto@example.com` (rol `recepcion`).
- **API real**: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8119` con `DATABASE_URL` apuntando a `turnos_c19_verify`.
- **Cliente**: script HTTP (`httpx`) que firma el access token con `emitir_access` del código de producción (mismo `JWT_SECRET` que la API). *Desviación*: se emitió el token directamente en vez de usar `POST /api/auth/login` porque el rate limiter de login es **fail-closed** sobre Redis (`rate_limit.py:51-53`) y este entorno no tiene Redis ni Docker disponibles; la validación de firma, vigencia y RBAC en cada request es la real de la API.

## Salidas

### Cliente HTTP (contra la API corriendo en :8119)

```text
POST /api/pacientes -> 201
  id: 17c2b47c-598b-4c4f-a2df-5af4e07dab49 | activo: True | ficha 1:1: True
POST /api/caja/cierre -> 201
POST /api/caja/movimientos -> 201
  id: f20c1588-1891-495c-a3b4-648961d986e1 | cierre_id: 7b79f4d9-e4b9-4789-b672-78907b0830d3 | monto: 1500.00
GET /api/pacientes?q=... -> 200 | encontrados: 1
```

### SELECT desde una sesión distinta (psql, después de las respuestas 201)

```text
         nombre          |   dni    | activo |          created_at
-------------------------+----------+--------+-------------------------------
 Manual C19 Verificacion | 99000111 | t      | 2026-11-16 22:49:10.511851-03
(1 fila)

 tiene_ficha
-------------
 t
(1 fila)

   fecha    | estado  | total_sistema
------------+----------+---------------
 2026-11-16 | abierto |          0.00
(1 fila)

  tipo    |        concepto         |  medio   |  monto  | vinculado_al_cierre
---------+-------------------------+----------+---------+---------------------
 ingreso | Verificacion manual C19 | efectivo | 1500.00 | t
(1 fila)

          accion           |     entidad
---------------------------+-----------------
 caja.registrar_movimiento | movimiento_caja
 caja.abrir                | cierre_caja
 paciente.crear            | paciente
 seed.inicial              | tenant
(4 filas)
```

## Conclusión

- El `POST /api/pacientes` **queda confirmado** en PostgreSQL (fila + ficha clínica 1:1) visible desde una sesión psql distinta: el commit del router C-19 funciona en el proceso real de uvicorn.
- El `POST /api/caja/movimientos` **queda confirmado** con su `cierre_id` vinculado y su auditoría `paciente.crear` / `caja.abrir` / `caja.registrar_movimiento` también visibles desde la sesión distinta.
- Limpieza: uvicorn detenido; la DB desechable `turnos_c19_verify` queda para consulta (se puede dropear cuando se desee).
