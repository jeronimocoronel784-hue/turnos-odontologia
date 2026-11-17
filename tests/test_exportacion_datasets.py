"""Exportación directa de datasets del consultorio (C-14, D4/D5).

Verifica CSV/JSON de los cuatro datasets, cabeceras exactas, enmascarado,
aislamiento de tenant y validaciones de parámetros.
"""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.caja import MovimientoCaja
from app.domain.liquidacion_os import LiquidacionOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario

URL = "/api/exportacion"


def _filas_csv(contenido: bytes) -> list[list[str]]:
    assert contenido.startswith(b"\xef\xbb\xbf")
    texto = contenido.decode("utf-8-sig")
    assert "\r\n" in texto
    return list(csv.reader(io.StringIO(texto, newline="")))


async def _dueno(api, session, tenant, crear_usuario, token_para, autorizacion):
    dueno = await crear_usuario(
        tenant=tenant, email=f"dueno-{uuid.uuid4()}@t.test", rol=RolUsuario.DUENO
    )
    return dueno, autorizacion(token_para(dueno))


async def test_dataset_invalido_422(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(f"{URL}/clinica", headers=headers)
    assert resp.status_code == 422


async def test_formato_invalido_422(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(f"{URL}/agenda", headers=headers, params={"formato": "xlsx"})
    assert resp.status_code == 422


async def test_rbac_recepcion_403(api, tenant_a, crear_usuario, token_para, autorizacion):
    recep = await crear_usuario(
        tenant=tenant_a, email=f"r-{uuid.uuid4()}@t.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recep))
    for ds in ("agenda", "pacientes", "caja", "liquidaciones"):
        for fmt in ("csv", "json"):
            resp = await api.get(f"{URL}/{ds}", headers=headers, params={"formato": fmt})
            assert resp.status_code == 403, (ds, fmt)


async def test_cabeceras_exactas_agenda(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    # seed un turno
    odonto = await crear_usuario(
        tenant=tenant_a, email=f"o-{uuid.uuid4()}@t.test", rol=RolUsuario.ODONTOLOGO
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Paciente Test",
        dni="12345678",
        telefono="111",
        activo=True,
    )
    sillon = Sillon(id=uuid.uuid4(), tenant_id=tenant_a.id, nombre="Box", activo=True)
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Consulta",
        duracion_min=30,
        precio_particular=Decimal("100"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([paciente, sillon, prestacion])
    await session.flush()
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=datetime(2026, 11, 5, 9, 0, tzinfo=UTC),
        fin=datetime(2026, 11, 5, 9, 30, tzinfo=UTC),
        estado=EstadoTurno.PENDIENTE.value,
        origen=OrigenTurno.PRESENCIAL.value,
        sobreturno=False,
    )
    session.add(turno)
    await session.flush()
    resp = await api.get(f"{URL}/agenda", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 200
    filas = _filas_csv(resp.content)
    assert filas[0] == [
        "turno_id",
        "inicio",
        "fin",
        "estado",
        "prestacion",
        "profesional",
        "matricula",
        "sillon",
        "paciente_id",
        "paciente_nombre",
        "sobreturno",
    ]
    assert len(filas) == 2
    assert resp.headers["cache-control"] == "no-store"
    assert "content-disposition" in resp.headers


async def test_cabeceras_exactas_pacientes(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    p = Paciente(
        id=uuid.uuid4(), tenant_id=tenant_a.id, nombre="P", dni="123", telefono="111", activo=True
    )
    session.add(p)
    await session.flush()
    resp = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 200
    filas = _filas_csv(resp.content)
    assert filas[0] == [
        "paciente_id",
        "nombre",
        "dni",
        "telefono",
        "email",
        "fecha_nac",
        "obra_social",
        "nro_afiliado",
        "optin_wa",
        "activo",
        "created_at",
    ]


async def test_cabeceras_exactas_caja(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    mov = MovimientoCaja(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        tipo="ingreso",
        concepto="Seña DNI 30.123.456",
        medio="efectivo",
        monto=Decimal("100.00"),
        created_by=dueno.id,
    )
    session.add(mov)
    await session.flush()
    resp = await api.get(f"{URL}/caja", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 200
    filas = _filas_csv(resp.content)
    assert filas[0] == [
        "movimiento_id",
        "created_at",
        "tipo",
        "concepto",
        "medio",
        "monto",
        "turno_id",
        "cierre_id",
    ]
    # enmascarado
    assert "30.123.456" not in resp.text
    assert "[dato oculto]" in resp.text


async def test_cabeceras_exactas_liquidaciones(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    liq = LiquidacionOS(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        obra_social="OSDE",
        periodo="202611",
        estado="borrador",
        total=Decimal("0"),
        total_reconocido=None,
        turnos_sin_cobertura=0,
        observaciones="CUIT 20-30123456-7",
        created_by=dueno.id,
    )
    session.add(liq)
    await session.flush()
    resp = await api.get(
        f"{URL}/liquidaciones",
        headers=headers,
        params={"formato": "csv", "desde": "2026-11-01", "hasta": "2026-11-17"},
    )
    assert resp.status_code == 200
    filas = _filas_csv(resp.content)
    assert filas[0] == [
        "liquidacion_id",
        "obra_social",
        "periodo",
        "estado",
        "total",
        "total_reconocido",
        "turnos_sin_cobertura",
        "observaciones",
        "created_at",
    ]
    assert "saldo_debito" not in filas[0]
    assert "20-30123456-7" not in resp.text
    assert "[dato oculto]" in resp.text


async def test_empty_dataset_200(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 200
    filas = _filas_csv(resp.content)
    assert len(filas) == 1
    resp2 = await api.get(f"{URL}/pacientes", headers=headers, params={"formato": "json"})
    assert resp2.status_code == 200
    assert resp2.json() == []


async def test_pacientes_ignora_rango(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    p = Paciente(
        id=uuid.uuid4(), tenant_id=tenant_a.id, nombre="P", dni="123", telefono="111", activo=True
    )
    session.add(p)
    await session.flush()
    r1 = await api.get(f"{URL}/pacientes", headers=headers)
    r2 = await api.get(
        f"{URL}/pacientes", headers=headers, params={"desde": "2020-01-01", "hasta": "2020-01-02"}
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.content == r2.content


async def test_tenant_isolation(
    api, session, tenant_a, tenant_b, crear_usuario, token_para, autorizacion
):
    # tenant A data
    pA = Paciente(
        id=uuid.uuid4(), tenant_id=tenant_a.id, nombre="PA", dni="111", telefono="1", activo=True
    )
    session.add(pA)
    # tenant B data
    pB = Paciente(
        id=uuid.uuid4(), tenant_id=tenant_b.id, nombre="PB", dni="222", telefono="2", activo=True
    )
    session.add(pB)
    await session.flush()
    duenoB = await crear_usuario(
        tenant=tenant_b, email=f"db-{uuid.uuid4()}@t.test", rol=RolUsuario.DUENO
    )
    headersB = autorizacion(token_para(duenoB))
    resp = await api.get(f"{URL}/pacientes", headers=headersB, params={"formato": "json"})
    assert resp.status_code == 200
    nombres = [r["nombre"] for r in resp.json()]
    assert "PA" not in nombres
    assert "PB" in nombres


async def test_nombre_archivo_sin_phi(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(f"{URL}/agenda", headers=headers)
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert "12345678" not in cd
    assert cd.startswith("attachment; ")


async def test_json_decimales_como_string(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    mov = MovimientoCaja(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        tipo="ingreso",
        concepto="x",
        medio="efectivo",
        monto=Decimal("123.45"),
        created_by=dueno.id,
    )
    session.add(mov)
    await session.flush()
    resp = await api.get(f"{URL}/caja", headers=headers, params={"formato": "json"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data[0]["monto"], str)


async def test_rango_desde_mayor_hasta_400(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(
        f"{URL}/caja", headers=headers, params={"desde": "2026-11-10", "hasta": "2026-11-01"}
    )
    assert resp.status_code == 400


async def test_rango_hasta_futuro_400(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    futuro = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    resp = await api.get(f"{URL}/caja", headers=headers, params={"hasta": futuro})
    assert resp.status_code == 400


async def test_rango_400_dias_400(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(
        f"{URL}/caja", headers=headers, params={"desde": "2025-06-01", "hasta": "2026-07-07"}
    )
    assert resp.status_code == 400


async def test_rango_fecha_mal_formada_400(api, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    r1 = await api.get(
        f"{URL}/caja", headers=headers, params={"desde": "31/11/2026", "hasta": "2026-11-16"}
    )
    r2 = await api.get(
        f"{URL}/caja", headers=headers, params={"desde": "2026-11-01", "hasta": "ayer"}
    )
    assert r1.status_code == 400
    assert r2.status_code == 400


async def test_exportacion_directa_registra_auditoria(
    api, session, tenant_a, crear_usuario, token_para, autorizacion, auditoria_de
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(f"{URL}/agenda", headers=headers, params={"formato": "csv"})
    assert resp.status_code == 200
    eventos = await auditoria_de("exportacion.solicitar")
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev.entidad == "exportacion"
    assert isinstance(ev.despues, dict)
    assert set(ev.despues.keys()) == {"dataset", "formato", "filas", "modo"}
    assert ev.despues["dataset"] == "agenda"
    assert ev.despues["formato"] == "csv"
    assert ev.despues["modo"] == "directo"


async def test_exportacion_falla_auditoria_no_entrega_archivo(
    monkeypatch, api, tenant_a, crear_usuario, token_para, autorizacion
):
    async def boom(*a, **k):
        raise RuntimeError("falla auditoria")

    monkeypatch.setattr("app.application.auditoria.registrar_auditoria", boom)
    # also patch router alias if present
    try:
        monkeypatch.setattr("app.api.routers.exportacion.registrar_auditoria", boom)
    except Exception:
        pass

    dueno, headers = await _dueno(api, None, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(f"{URL}/agenda", headers=headers, params={"formato": "csv"})
    assert resp.status_code in (500, 503)
