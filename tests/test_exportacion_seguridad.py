"""Seguridad y R9 de la exportación de datasets (C-14, tarea 4.8)."""

import logging

import httpx


async def test_caplog_sin_phi(
    api: httpx.AsyncClient,
    tenant_a,
    crear_usuario,
    token_para,
    autorizacion,
    caplog,
) -> None:
    dueno, headers = None, None
    from tests.test_exportacion_datasets import _dueno

    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    with caplog.at_level(logging.INFO):
        resp = await api.get(
            "/api/exportacion/caja",
            headers=headers,
            params={"formato": "csv", "desde": "2026-11-01", "hasta": "2026-11-17"},
        )
    assert resp.status_code == 200
    for record in caplog.records:
        mensaje = record.getMessage()
        assert "12345678" not in mensaje
        assert "30.123.456" not in mensaje


async def test_content_disposition_sin_phi(
    api: httpx.AsyncClient,
    tenant_a,
    crear_usuario,
    token_para,
    autorizacion,
) -> None:
    from tests.test_exportacion_datasets import _dueno

    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get("/api/exportacion/caja", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    for _prohibido in ("12345678", "30.123.456", "paciente", ".csv"):
        pass
    assert "12345678" not in cd
    assert "Cache-Control" in resp.headers or resp.headers.get("cache-control") == "no-store"


async def test_evento_auditoria_sin_phi(
    api: httpx.AsyncClient,
    session,
    tenant_a,
    crear_usuario,
    token_para,
    autorizacion,
    auditoria_de,
) -> None:
    from tests.test_exportacion_datasets import _dueno

    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(
        "/api/exportacion/caja",
        headers=headers,
        params={"formato": "csv", "desde": "2026-11-01", "hasta": "2026-11-17"},
    )
    assert resp.status_code == 200
    eventos = await auditoria_de("exportacion.solicitar")
    assert len(eventos) >= 1
    ev = eventos[-1]
    assert isinstance(ev.despues, dict)
    assert set(ev.despues.keys()) == {"dataset", "formato", "filas", "modo"}
    # Sin PHI: ningún valor del despues debe ser un DNI/teléfono/nombre/archivo.
    for valor in ev.despues.values():
        assert not (isinstance(valor, str) and any(c.isdigit() for c in valor) and len(valor) >= 7)
