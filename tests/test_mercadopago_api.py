"""Tests de los endpoints administrativos de Mercado Pago (tarea 3.2).

Cubre:
- `GET /api/pagos/mercadopago/cobros` y `/discrepancias` bajo `Recurso.CAJA`.
- Dueño y Recepción acceden; Odontólogo recibe `403` (matriz RBAC §03).
- R4: sólo se listan cobros del tenant del token, aunque existan de otro consultorio.
- Filtros básicos (`estado_conciliacion`, `sena_id`) y motivo de discrepancia visible.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda import crear_turno
from app.domain.caja import EstadoSena, Sena
from app.domain.mercadopago import CobroMP, EstadoConciliacionMP, EstadoMP
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno
from app.domain.usuario import RolUsuario, Usuario

MONTO_SENA = Decimal("10000.00")


async def _preparar_escenario(
    session: AsyncSession,
    tenant: Tenant,
    *,
    etiqueta: str = "a",
    inicio: datetime = datetime(2026, 12, 4, 10, 0, tzinfo=UTC),
) -> SimpleNamespace:
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-api-mp-{tenant.slug}-{etiqueta}@test.com",
        nombre="Dr. API MP",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-50501",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Paciente API MP {etiqueta}",
        dni=f"44{uuid.uuid4().int % 10**7:07d}",
        telefono=f"+54911777{uuid.uuid4().int % 10**6:06d}",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Box API MP {etiqueta}",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Implante API MP {etiqueta}",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=True,
        monto_sena=MONTO_SENA,
        invasiva=False,
        activa=True,
    )
    session.add_all([odontologo, paciente, sillon, prestacion])
    await session.flush()

    turno, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=inicio,
        actor_id=odontologo.id,
    )
    await session.flush()
    sena = (await session.execute(select_sena(turno.id))).scalar_one()
    return SimpleNamespace(tenant=tenant, odontologo=odontologo, turno=turno, sena=sena)


def select_sena(turno_id: uuid.UUID):  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    return select(Sena).where(Sena.turno_id == turno_id)


def _cobro(
    ctx: SimpleNamespace,
    payment_id: str,
    *,
    estado_mp: str = EstadoMP.APPROVED.value,
    estado_conciliacion: str = EstadoConciliacionMP.CONCILIADO.value,
    monto: Decimal = MONTO_SENA,
) -> CobroMP:
    return CobroMP(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant.id,
        turno_id=ctx.turno.id,
        sena_id=ctx.sena.id,
        mp_payment_id=payment_id,
        mp_preference_id="pref_api_001",
        monto=monto,
        estado_mp=estado_mp,
        estado_conciliacion=estado_conciliacion,
        payload={"data": {"id": payment_id, "status": estado_mp}},
    )


async def test_dueno_y_recepcion_consultan_cobros_y_discrepancias_del_tenant(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RBAC Dueño/Recepción + filtros + aislamiento multi-tenant (R4)."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-api-mp@test.com", rol=RolUsuario.DUENO
    )
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-api-mp@test.com", rol=RolUsuario.RECEPCION
    )
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-api-mp-rbac@test.com", rol=RolUsuario.ODONTOLOGO
    )
    dueno_b = await crear_usuario(
        tenant=tenant_b, email="dueno-api-mp-b@test.com", rol=RolUsuario.DUENO
    )

    ok = await _preparar_escenario(session, tenant_a, etiqueta="ok")
    tardio = await _preparar_escenario(
        session,
        tenant_a,
        etiqueta="tardio",
        inicio=datetime(2026, 12, 4, 11, 30, tzinfo=UTC),
    )
    ajeno = await _preparar_escenario(
        session,
        tenant_b,
        etiqueta="ajeno",
        inicio=datetime(2026, 12, 4, 12, 30, tzinfo=UTC),
    )

    tardio.sena.estado = EstadoSena.VENCIDA.value
    tardio.turno.estado = EstadoTurno.CANCELADO.value
    cobro_ok = _cobro(ok, "mp-api-ok-001")
    cobro_disc = _cobro(
        tardio,
        "mp-api-disc-002",
        estado_conciliacion=EstadoConciliacionMP.DISCREPANCIA.value,
    )
    cobro_ajeno = _cobro(ajeno, "mp-api-ajeno-003")
    session.add_all([cobro_ok, cobro_disc, cobro_ajeno])
    await session.flush()

    headers_dueno = autorizacion(token_para(dueno))
    headers_recepcion = autorizacion(token_para(recepcion))
    headers_odonto = autorizacion(token_para(odontologo))
    headers_dueno_b = autorizacion(token_para(dueno_b))

    # Dueño y Recepción listan sólo los cobros del tenant A.
    for headers in (headers_dueno, headers_recepcion):
        resp = await api.get("/api/pagos/mercadopago/cobros", headers=headers)
        assert resp.status_code == 200, resp.text
        ids = {c["id"] for c in resp.json()}
        assert ids == {str(cobro_ok.id), str(cobro_disc.id)}
        assert {c["tenant_id"] for c in resp.json()} == {str(tenant_a.id)}

    # Filtros básicos.
    resp_disc = await api.get(
        "/api/pagos/mercadopago/cobros",
        headers=headers_recepcion,
        params={"estado_conciliacion": EstadoConciliacionMP.DISCREPANCIA.value},
    )
    assert resp_disc.status_code == 200
    assert [c["id"] for c in resp_disc.json()] == [str(cobro_disc.id)]

    resp_sena = await api.get(
        "/api/pagos/mercadopago/cobros",
        headers=headers_recepcion,
        params={"sena_id": str(ok.sena.id)},
    )
    assert resp_sena.status_code == 200
    assert [c["id"] for c in resp_sena.json()] == [str(cobro_ok.id)]

    # Discrepancias: motivo visible y datos del cobro pendiente de resolución manual.
    resp_discrepancias = await api.get(
        "/api/pagos/mercadopago/discrepancias", headers=headers_recepcion
    )
    assert resp_discrepancias.status_code == 200, resp_discrepancias.text
    discrepancias = resp_discrepancias.json()
    assert len(discrepancias) == 1
    assert discrepancias[0]["id"] == str(cobro_disc.id)
    assert discrepancias[0]["mp_payment_id"] == cobro_disc.mp_payment_id
    assert "vencida" in discrepancias[0]["motivo"].lower()

    # R4: el dueño del tenant B no ve nada del A.
    resp_b = await api.get("/api/pagos/mercadopago/cobros", headers=headers_dueno_b)
    assert resp_b.status_code == 200
    assert [c["id"] for c in resp_b.json()] == [str(cobro_ajeno.id)]

    # RBAC: Odontólogo sólo lectura de caja no incluye la conciliación? La matriz le da
    # `LEER` sobre `Recurso.CAJA`; los endpoints de auditoría de MP exigen Dueño/Recepción.
    for ruta in ("/api/pagos/mercadopago/cobros", "/api/pagos/mercadopago/discrepancias"):
        resp_403 = await api.get(ruta, headers=headers_odonto)
        assert resp_403.status_code == 403, f"{ruta}: {resp_403.text}"
