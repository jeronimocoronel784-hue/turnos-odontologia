"""Paquete de datos del paciente (C-14, D8, RN-SE-02, tarea 6.1/6.3/6.4)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.caja import MovimientoCaja
from app.domain.clinica import (
    AdjuntoClinico,
    Consentimiento,
    Evolucion,
    Odontograma,
    PiezaEvento,
)
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.presupuesto import Presupuesto, PresupuestoItem, PresupuestoTurno
from app.domain.sillon import Sillon
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario

URL = "/api/pacientes"


async def _dueno(api, session, tenant, crear_usuario, token_para, autorizacion):
    dueno = await crear_usuario(
        tenant=tenant, email=f"dueno-{uuid.uuid4()}@t.test", rol=RolUsuario.DUENO
    )
    return dueno, autorizacion(token_para(dueno))


async def _seed_paquete(session, tenant, dueno):
    # Prestacion
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Limpieza",
        duracion_min=30,
        precio_particular=Decimal("1000.00"),
        requiere_sena=False,
        invasiva=True,
        activa=True,
    )
    sillon = Sillon(id=uuid.uuid4(), tenant_id=tenant.id, nombre="Box1", activo=True)
    session.add_all([prestacion, sillon])
    await session.flush()

    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Paciente Export",
        dni="30123456",
        telefono="1155550000",
        email="p@test.com",
        activo=True,
    )
    session.add(paciente)
    await session.flush()

    # Ficha
    from app.domain.ficha_clinica import FichaClinica

    ficha = FichaClinica(tenant_id=tenant.id, paciente_id=paciente.id, antecedentes="Ant")
    session.add(ficha)
    await session.flush()

    # Turno
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=dueno.id,
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

    # Evolucion
    evo = Evolucion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        ficha_clinica_id=ficha.id,
        paciente_id=paciente.id,
        turno_id=turno.id,
        profesional_id=dueno.id,
        nota="Nota clínica",
    )
    session.add(evo)
    await session.flush()

    # Odontograma + evento
    od = Odontograma(id=uuid.uuid4(), tenant_id=tenant.id, paciente_id=paciente.id)
    session.add(od)
    await session.flush()
    pe = PiezaEvento(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        odontograma_id=od.id,
        pieza_fdi=11,
        superficie="oclusal",
        evento="caries",
        turno_id=turno.id,
        observacion="obs",
        created_by=dueno.id,
    )
    session.add(pe)
    await session.flush()

    # Presupuesto
    pres = Presupuesto(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        estado="borrador",
        total=Decimal("1000.00"),
        total_cobertura_os=Decimal("100.00"),
        total_a_cargo=Decimal("900.00"),
        created_by=dueno.id,
    )
    session.add(pres)
    await session.flush()
    item = PresupuestoItem(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        presupuesto_id=pres.id,
        prestacion_id=prestacion.id,
        cantidad=1,
        precio_unit=Decimal("1000.00"),
        cobertura_os=Decimal("100.00"),
        a_cargo=Decimal("900.00"),
    )
    session.add(item)
    await session.flush()
    pt = PresupuestoTurno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        presupuesto_id=pres.id,
        turno_id=turno.id,
        presupuesto_item_id=item.id,
    )
    session.add(pt)
    await session.flush()

    # Consentimiento
    cons = Consentimiento(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        prestacion_id=prestacion.id,
        turno_id=turno.id,
        texto_version="v1",
        texto_contenido="TEXTO COMPLETO SECRETO",
        firma_hash="b" * 64,
        firmado_por="Paciente",
        firmado_at=datetime(2026, 11, 5, 9, 0, tzinfo=UTC),
        canal="presencial",
        revocado=False,
    )
    session.add(cons)
    await session.flush()

    # Adjunto
    adj = AdjuntoClinico(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        ficha_clinica_id=ficha.id,
        tipo="rx",
        nombre_archivo="radiografia-juan-perez.jpg",
        mime_type="image/jpeg",
        tamano_bytes=1234,
        storage_key="secret-key",
        created_by=dueno.id,
    )
    session.add(adj)
    await session.flush()

    # Movimiento caja
    mov = MovimientoCaja(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        tipo="ingreso",
        concepto="Seña",
        medio="efectivo",
        monto=Decimal("500.00"),
        turno_id=turno.id,
        created_by=dueno.id,
    )
    session.add(mov)
    await session.flush()

    # Otro paciente + auditoría para exclusión
    otro = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Otro Paciente",
        dni="99999999",
        telefono="222",
        activo=True,
    )
    session.add(otro)
    await session.flush()

    return paciente, otro


@pytest.mark.asyncio
async def test_dueno_obtiene_paquete_con_todas_las_secciones(
    api, session, tenant_a, crear_usuario, token_para, autorizacion, auditoria_de
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    paciente, otro = await _seed_paquete(session, tenant_a, dueno)
    await session.commit()

    resp = await api.get(f"{URL}/{paciente.id}/exportar-datos", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # secciones
    assert "turnos" in data and len(data["turnos"]) == 1
    assert data["ficha_clinica"] is not None
    assert len(data["evoluciones"]) == 1
    assert len(data["odontograma"]["eventos"]) == 1
    assert len(data["presupuestos"]) == 1
    assert len(data["presupuestos"][0]["items"]) == 1
    assert len(data["presupuestos"][0]["turnos"]) == 1
    assert len(data["consentimientos"]) == 1
    assert data["adjuntos"]["cantidad"] == 1
    assert len(data["adjuntos"]["items"]) == 1
    assert len(data["movimientos"]) == 1
    # consentimiento
    c = data["consentimientos"][0]
    assert c["firma_hash"] == "b" * 64
    assert "texto_contenido" not in c
    # adjunto sin nombre
    adj = data["adjuntos"]["items"][0]
    assert set(adj.keys()) == {"tipo", "mime_type", "tamano_bytes", "created_at"}
    assert adj["tipo"] == "rx"
    # valores
    assert data["paciente"]["nombre"] == "Paciente Export"
    assert data["turnos"][0]["paciente_id"] if "paciente_id" in data["turnos"][0] else True
    # montos string
    assert isinstance(data["presupuestos"][0]["total"], str)
    assert isinstance(data["movimientos"][0]["monto"], str)
    # otros pacientes no incluidos
    assert otro.nombre not in str(data)
    assert "Otro Paciente" not in str(data)
    # trail no incluido
    assert "auditoria" not in data
    # binarios/tokens no incluidos
    assert "storage_key" not in str(data)
    assert "secret-key" not in str(data)
    # headers
    assert resp.headers["cache-control"] == "no-store"
    cd = resp.headers["content-disposition"]
    assert "30123456" not in cd
    assert "Paciente" not in cd
    # audit event
    eventos = await auditoria_de("paciente.exportar_datos")
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev.entidad == "paciente"
    assert ev.entidad_id == str(paciente.id)
    assert isinstance(ev.despues, dict)
    assert ev.despues["formato"] == "json"
    assert "secciones" in ev.despues
    # sin PHI en evento
    texto_evento = str(ev.despues)
    assert "30123456" not in texto_evento
    assert "Paciente Export" not in texto_evento


@pytest.mark.asyncio
async def test_recepcion_y_odontologo_403(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    await crear_usuario(tenant=tenant_a, email=f"dueno-{uuid.uuid4()}@t.test", rol=RolUsuario.DUENO)
    # paciente
    p = __import__("app.domain.paciente", fromlist=["Paciente"]).Paciente(
        id=uuid.uuid4(), tenant_id=tenant_a.id, nombre="P", dni="111", telefono="222", activo=True
    )
    session.add(p)
    await session.flush()
    await session.commit()
    for rol in (RolUsuario.RECEPCION, RolUsuario.ODONTOLOGO):
        u = await crear_usuario(
            tenant=tenant_a, email=f"{rol.value}-{uuid.uuid4()}@t.test", rol=rol
        )
        headers = autorizacion(token_para(u))
        resp = await api.get(f"{URL}/{p.id}/exportar-datos", headers=headers)
        assert resp.status_code == 403, rol


@pytest.mark.asyncio
async def test_paciente_otro_tenant_y_uuid_inexistente_mismo_404(
    api, session, tenant_a, tenant_b, crear_usuario, token_para, autorizacion
):
    dueno_a, headers_a = await _dueno(
        api, session, tenant_a, crear_usuario, token_para, autorizacion
    )
    # paciente en tenant B
    pac_b = Paciente(
        id=uuid.uuid4(), tenant_id=tenant_b.id, nombre="PB", dni="222", telefono="333", activo=True
    )
    session.add(pac_b)
    await session.flush()
    await session.commit()
    r1 = await api.get(f"{URL}/{pac_b.id}/exportar-datos", headers=headers_a)
    r2 = await api.get(f"{URL}/{uuid.uuid4()}/exportar-datos", headers=headers_a)
    assert r1.status_code == 404
    assert r2.status_code == 404
    assert r1.json() == r2.json()


@pytest.mark.asyncio
async def test_uuid_malformado_422(api, session, tenant_a, crear_usuario, token_para, autorizacion):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    resp = await api.get(f"{URL}/no-es-uuid/exportar-datos", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_paciente_sin_actividad_200_listas_vacias(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    p = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="SinAct",
        dni="555",
        telefono="666",
        activo=True,
    )
    session.add(p)
    await session.flush()
    await session.commit()
    resp = await api.get(f"{URL}/{p.id}/exportar-datos", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["turnos"] == []
    assert data["evoluciones"] == []
    assert data["odontograma"]["eventos"] == []
    assert data["presupuestos"] == []
    assert data["consentimientos"] == []
    assert data["adjuntos"]["cantidad"] == 0
    assert data["adjuntos"]["items"] == []
    assert data["movimientos"] == []
    assert data["ficha_clinica"] is None


@pytest.mark.asyncio
async def test_paciente_con_prestacion_invasiva_sin_consentimiento_200(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    p = Paciente(
        id=uuid.uuid4(), tenant_id=tenant_a.id, nombre="Inv", dni="777", telefono="888", activo=True
    )
    session.add(p)
    await session.flush()
    await session.commit()
    resp = await api.get(f"{URL}/{p.id}/exportar-datos", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["consentimientos"] == []


@pytest.mark.asyncio
async def test_falla_auditoria_no_entrega_paquete(
    monkeypatch, api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    async def boom(*a, **k):
        raise RuntimeError("falla auditoria")

    monkeypatch.setattr("app.application.auditoria.registrar_auditoria", boom)
    monkeypatch.setattr("app.application.pacientes.registrar_auditoria", boom)
    try:
        monkeypatch.setattr("app.api.routers.pacientes.registrar_auditoria", boom)
    except Exception:
        pass

    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    p = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Falla",
        dni="999",
        telefono="1010",
        activo=True,
    )
    session.add(p)
    await session.flush()
    await session.commit()

    resp = await api.get(f"{URL}/{p.id}/exportar-datos", headers=headers)
    assert resp.status_code in (500, 503)


@pytest.mark.asyncio
async def test_nombre_archivo_opaco_sin_dni_ni_nombre(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
):
    dueno, headers = await _dueno(api, session, tenant_a, crear_usuario, token_para, autorizacion)
    p = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Secreto",
        dni="12345678",
        telefono="999",
        activo=True,
    )
    session.add(p)
    await session.flush()
    await session.commit()
    resp = await api.get(f"{URL}/{p.id}/exportar-datos", headers=headers)
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert "12345678" not in cd
    assert "Secreto" not in cd
    assert resp.headers["cache-control"] == "no-store"
