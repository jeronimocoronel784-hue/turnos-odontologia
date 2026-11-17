"""Exportación asíncrona con descarga (C-14, D6)."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import app.workers.main as worker_mod
from app.application import exportacion as _exp
from app.domain.auditoria import Auditoria
from app.domain.paciente import Paciente
from app.domain.usuario import RolUsuario
from app.shared.settings import Settings

URL = "/api/exportacion"


async def _dueno(api, session, tenant, crear_usuario, token_para, autorizacion):
    dueno = await crear_usuario(
        tenant=tenant, email=f"dueno-{uuid.uuid4()}@t.test", rol=RolUsuario.DUENO
    )
    return dueno, autorizacion(token_para(dueno))


@pytest.mark.asyncio
async def test_umbral_directo_sin_job(
    monkeypatch, api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    monkeypatch.setattr(_exp, "EXPORTACION_UMBRAL_FILAS", 2)
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    for i in range(2):
        session.add(
            Paciente(
                id=uuid.uuid4(),
                tenant_id=tenant_a.id,
                nombre=f"P{i}",
                dni=str(i),
                telefono="1",
                activo=True,
            )
        )
    await session.flush()

    resp = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_umbral_encola_job(
    monkeypatch, api, session, tenant_a, crear_usuario, token_para, autorizacion, redis_fake
):
    monkeypatch.setattr(_exp, "EXPORTACION_UMBRAL_FILAS", 2)
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    for i in range(3):
        session.add(
            Paciente(
                id=uuid.uuid4(),
                tenant_id=tenant_a.id,
                nombre=f"P{i}",
                dni=str(i),
                telefono="1",
                activo=True,
            )
        )
    await session.flush()

    resp = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 202
    data = resp.json()
    assert data["estado"] == "pendiente"
    assert data["job_id"]
    rdata = await redis_fake.hgetall(_exp.clave_job(tenant_a.id, data["job_id"]))
    assert rdata
    assert rdata["estado"] == "pendiente"


@pytest.mark.asyncio
async def test_descarga_antes_de_listo_409(
    api, tenant_a, crear_usuario, token_para, autorizacion, redis_fake
):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    job_id = str(uuid.uuid4())
    await redis_fake.hset(
        _exp.clave_job(tenant_a.id, job_id),
        mapping={
            "estado": "pendiente",
            "dataset": "agenda",
            "formato": "csv",
            "filas": "10",
            "creado_at": datetime.now(UTC).isoformat(),
            "expira_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "nombre_archivo": "",
            "error": "",
        },
    )
    await redis_fake.expire(_exp.clave_job(tenant_a.id, job_id), 3600)
    resp = await api.get(f"{URL}/jobs/{job_id}/descarga", headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_worker_falla_error_409(
    api, tenant_a, crear_usuario, token_para, autorizacion, redis_fake
):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    job_id = str(uuid.uuid4())
    await redis_fake.hset(
        _exp.clave_job(tenant_a.id, job_id),
        mapping={
            "estado": "error",
            "dataset": "agenda",
            "formato": "csv",
            "filas": "10",
            "creado_at": datetime.now(UTC).isoformat(),
            "expira_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "nombre_archivo": "",
            "error": "boom",
        },
    )
    await redis_fake.expire(_exp.clave_job(tenant_a.id, job_id), 3600)
    resp = await api.get(f"{URL}/jobs/{job_id}/descarga", headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_job_status_endpoint(
    api, tenant_a, crear_usuario, token_para, autorizacion, redis_fake
):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    job_id = str(uuid.uuid4())
    await redis_fake.hset(
        _exp.clave_job(tenant_a.id, job_id),
        mapping={
            "estado": "pendiente",
            "dataset": "agenda",
            "formato": "csv",
            "filas": "10",
            "creado_at": datetime.now(UTC).isoformat(),
            "expira_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "nombre_archivo": "",
            "error": "",
        },
    )
    await redis_fake.expire(_exp.clave_job(tenant_a.id, job_id), 3600)
    resp = await api.get(f"{URL}/jobs/{job_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["estado"] == "pendiente"


@pytest.mark.asyncio
async def test_redis_caido_al_crear_job_503(
    monkeypatch, api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    monkeypatch.setattr(_exp, "EXPORTACION_UMBRAL_FILAS", 0)

    class BadRedis:
        async def hset(self, *a, **k):
            raise RuntimeError("redis down")

        async def expire(self, *a, **k):
            raise RuntimeError("redis down")

        async def delete(self, *a, **k):
            return 0

        async def rpush(self, *a, **k):
            return 0

    from app.api import deps

    api._transport.app.dependency_overrides[deps.cliente_redis] = lambda: BadRedis()
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    session.add(
        Paciente(
            id=uuid.uuid4(), tenant_id=tenant_a.id, nombre="P", dni="1", telefono="1", activo=True
        )
    )
    await session.flush()

    resp = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 503
    del api._transport.app.dependency_overrides[deps.cliente_redis]


@pytest.mark.asyncio
async def test_job_otro_tenant_404(
    api, tenant_a, tenant_b, crear_usuario, token_para, autorizacion, redis_fake
):
    duenoA = await crear_usuario(
        tenant=tenant_a, email=f"da-{uuid.uuid4()}@t.test", rol=RolUsuario.DUENO
    )
    headersA = autorizacion(token_para(duenoA))
    job_id = str(uuid.uuid4())
    await redis_fake.hset(
        _exp.clave_job(tenant_b.id, job_id),
        mapping={
            "estado": "listo",
            "dataset": "agenda",
            "formato": "csv",
            "filas": "10",
            "creado_at": datetime.now(UTC).isoformat(),
            "expira_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "nombre_archivo": f"{job_id}.csv",
            "error": "",
        },
    )
    await redis_fake.expire(_exp.clave_job(tenant_b.id, job_id), 3600)
    resp = await api.get(f"{URL}/jobs/{job_id}", headers=headersA)
    assert resp.status_code == 404
    resp2 = await api.get(f"{URL}/jobs/{job_id}/descarga", headers=headersA)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_job_vencido_404(api, tenant_a, crear_usuario, token_para, autorizacion, redis_fake):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    job_id = str(uuid.uuid4())
    await redis_fake.hset(
        _exp.clave_job(tenant_a.id, job_id),
        mapping={
            "estado": "listo",
            "dataset": "agenda",
            "formato": "csv",
            "filas": "10",
            "creado_at": (datetime.now(UTC) - timedelta(hours=25)).isoformat(),
            "expira_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "nombre_archivo": f"{job_id}.csv",
            "error": "",
        },
    )
    await redis_fake.expire(_exp.clave_job(tenant_a.id, job_id), 3600)
    resp = await api.get(f"{URL}/jobs/{job_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_job_listo_archivo_borrado_404(
    api, tenant_a, crear_usuario, token_para, autorizacion, redis_fake
):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    job_id = str(uuid.uuid4())
    await redis_fake.hset(
        _exp.clave_job(tenant_a.id, job_id),
        mapping={
            "estado": "listo",
            "dataset": "agenda",
            "formato": "csv",
            "filas": "10",
            "creado_at": datetime.now(UTC).isoformat(),
            "expira_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "nombre_archivo": f"{job_id}.csv",
            "error": "",
        },
    )
    await redis_fake.expire(_exp.clave_job(tenant_a.id, job_id), 3600)
    resp = await api.get(f"{URL}/jobs/{job_id}/descarga", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_worker_marca_listo_descarga_devuelve_archivo(
    api, tenant_a, crear_usuario, token_para, autorizacion, redis_fake, monkeypatch, tmp_path
):
    export_dir = str(tmp_path / "exportaciones")
    os.makedirs(export_dir, exist_ok=True)
    monkeypatch.setattr(_exp, "EXPORTACIONES_DIR", export_dir)
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    job_id = str(uuid.uuid4())
    with open(os.path.join(export_dir, f"{job_id}.csv"), "w") as f:  # noqa: ASYNC230
        f.write("a,b\n1,2\n")
    await redis_fake.hset(
        _exp.clave_job(tenant_a.id, job_id),
        mapping={
            "estado": "listo",
            "dataset": "agenda",
            "formato": "csv",
            "filas": "10",
            "creado_at": datetime.now(UTC).isoformat(),
            "expira_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "nombre_archivo": f"{job_id}.csv",
            "error": "",
        },
    )
    await redis_fake.expire(_exp.clave_job(tenant_a.id, job_id), 3600)
    resp = await api.get(f"{URL}/jobs/{job_id}/descarga", headers=headers)
    assert resp.status_code == 200
    assert b"1,2" in resp.content


@pytest.mark.asyncio
async def test_worker_exporta_dataset_marca_listo(
    monkeypatch, tmp_path, redis_fake, db_url, tenant_a
):
    export_dir = str(tmp_path / "exportaciones")
    os.makedirs(export_dir, exist_ok=True)
    monkeypatch.setattr(_exp, "EXPORTACIONES_DIR", export_dir)
    settings = Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/0",
        jwt_secret="secreto-de-test-con-mas-de-32-caracteres-ok",
    )
    job_id = str(uuid.uuid4())
    key = _exp.clave_job(tenant_a.id, job_id)
    await redis_fake.hset(
        key,
        mapping={
            "estado": "pendiente",
            "dataset": "pacientes",
            "formato": "csv",
            "filas": "0",
            "creado_at": datetime.now(UTC).isoformat(),
            "expira_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "nombre_archivo": "",
            "error": "",
        },
    )
    await redis_fake.expire(key, 3600)

    payload = {
        "tipo": "exportar_dataset",
        "job_id": job_id,
        "tenant_id": str(tenant_a.id),
        "actor_id": str(tenant_a.id),
        "dataset": "pacientes",
        "formato": "csv",
        "desde": None,
        "hasta": None,
    }
    await worker_mod.procesar_job(payload, redis=redis_fake, settings=settings)

    data = await redis_fake.hgetall(key)
    assert data["estado"] == "listo"
    assert os.path.exists(os.path.join(export_dir, f"{job_id}.csv"))  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_async_exportacion_auditoria_un_evento(
    monkeypatch, api, session, tenant_a, crear_usuario, token_para, autorizacion, redis_fake, db_url
):
    monkeypatch.setattr(_exp, "EXPORTACION_UMBRAL_FILAS", -1)
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    session.add(
        Paciente(
            id=__import__("uuid").uuid4(),
            tenant_id=tenant_a.id,
            nombre="P",
            dni="1",
            telefono="1",
            activo=True,
        )
    )
    await session.flush()

    resp = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Worker procesa el job pero NO duplica el evento de auditoría.
    settings = Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/0",
        jwt_secret="secreto-de-test-con-mas-de-32-caracteres-ok",
    )
    payload = {
        "tipo": "exportar_dataset",
        "job_id": job_id,
        "tenant_id": str(tenant_a.id),
        "actor_id": str(dueno.id),
        "dataset": "pacientes",
        "formato": "csv",
        "desde": None,
        "hasta": None,
    }
    await worker_mod.procesar_job(payload, redis=redis_fake, settings=settings)

    await session.commit()
    eventos = list(
        (
            await session.execute(
                select(Auditoria).where(Auditoria.accion == "exportacion.solicitar")
            )
        )
        .scalars()
        .all()
    )
    assert len(eventos) == 1
    assert eventos[0].entidad_id == job_id
    assert (eventos[0].despues or {}).get("modo") == "asincronico"
    assert "job_id" not in (eventos[0].despues or {})


@pytest.mark.asyncio
async def test_pedido_repetido_auditoria_dos_eventos_dos_jobs(
    monkeypatch, api, session, tenant_a, crear_usuario, token_para, autorizacion, redis_fake
):
    monkeypatch.setattr(_exp, "EXPORTACION_UMBRAL_FILAS", -1)
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    session.add(
        Paciente(
            id=__import__("uuid").uuid4(),
            tenant_id=tenant_a.id,
            nombre="P",
            dni="1",
            telefono="1",
            activo=True,
        )
    )
    await session.flush()

    r1 = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    r2 = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    assert r1.status_code == 202 and r2.status_code == 202
    assert r1.json()["job_id"] != r2.json()["job_id"]

    await session.commit()
    eventos = list(
        (
            await session.execute(
                select(Auditoria).where(Auditoria.accion == "exportacion.solicitar")
            )
        )
        .scalars()
        .all()
    )
    assert len(eventos) == 2
