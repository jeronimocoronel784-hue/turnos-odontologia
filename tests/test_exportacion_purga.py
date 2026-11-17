"""Purga de archivos de exportación vencidos (C-14, D6, 5.5)."""

import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

import app.application.exportacion as _exp


@pytest.mark.asyncio
async def test_purga_archivo_vencido(tmp_path, monkeypatch):
    export_dir = str(tmp_path / "exportaciones")
    os.makedirs(export_dir, exist_ok=True)
    archivo = os.path.join(export_dir, "viejo.csv")
    with open(archivo, "w") as fh:  # noqa: ASYNC230
        fh.write("a,b\n1,2\n")
    viejo = time.time() - 25 * 3600
    os.utime(archivo, (viejo, viejo))
    monkeypatch.setattr(_exp, "EXPORTACIONES_DIR", export_dir)

    await _exp.purgar_exportaciones_vencidas()

    assert not os.path.exists(archivo)  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_purga_conserva_reciente(tmp_path, monkeypatch):
    export_dir = str(tmp_path / "exportaciones")
    os.makedirs(export_dir, exist_ok=True)
    archivo = os.path.join(export_dir, "nuevo.csv")
    with open(archivo, "w") as fh:  # noqa: ASYNC230
        fh.write("a,b\n1,2\n")
    monkeypatch.setattr(_exp, "EXPORTACIONES_DIR", export_dir)

    await _exp.purgar_exportaciones_vencidas()

    assert os.path.exists(archivo)  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_worker_barre_al_arrancar(monkeypatch):
    import app.workers.main as worker

    llamadas: list[int] = []

    async def fake_purga():
        llamadas.append(1)

    monkeypatch.setattr(_exp, "purgar_exportaciones_vencidas", fake_purga)
    monkeypatch.setattr(worker, "_ultima_purga_monotonic", 0.0)

    await worker._purgar_si_corresponde(force=True)
    assert llamadas == [1]


@pytest.mark.asyncio
async def test_job_vencido_descarga_404(
    api, tenant_a, crear_usuario, token_para, autorizacion, redis_fake
):
    dueno, headers = await _make_dueno(api, tenant_a, crear_usuario, token_para, autorizacion)
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
    resp = await api.get(f"/api/exportacion/jobs/{job_id}/descarga", headers=headers)
    assert resp.status_code == 404


async def _make_dueno(api, tenant, crear_usuario, token_para, autorizacion):
    from app.domain.usuario import RolUsuario

    dueno = await crear_usuario(
        tenant=tenant, email=f"dueno-{uuid.uuid4()}@t.test", rol=RolUsuario.DUENO
    )
    return dueno, autorizacion(token_para(dueno))
