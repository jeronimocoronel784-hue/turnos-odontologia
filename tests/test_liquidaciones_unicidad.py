"""Unicidad del turno en liquidaciones abiertas (`RN-OS-02`, C-13 tarea 3.5).

Verifica la garantía en las dos capas exigidas por el design (D3/D6):
1. Caso de uso: 409 al repetir el borrador por OS/período y al incluir un turno que ya vive en
   otra liquidación abierta.
2. Base de datos: el índice único parcial `uq_liquidacion_detalle_turno_abierto` sólo bloquea
   las filas `vigente`, deja convivir OS/períodos distintos y libera el turno al anular o pagar.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_liquidaciones import LiquidacionOSAnularInput, LiquidacionOSCreate
from app.application.liquidaciones import (
    anular_liquidacion,
    generar_borrador,
    presentar_liquidacion,
)
from app.domain.cobertura_os import CoberturaOS
from app.domain.liquidacion_os import (
    EstadoLiquidacionOS,
    LiquidacionOS,
    LiquidacionOSDetalle,
)
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario
from app.shared.exceptions import Conflicto

INICIO = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


class _Consultorio:
    def __init__(self) -> None:
        self.usuario: Usuario
        self.paciente: Paciente
        self.sillon: Sillon
        self.prestacion: Prestacion


async def _seed(session: AsyncSession, tenant: Tenant) -> _Consultorio:
    """Un turno liquidable contra dos obras sociales con convenio vigente."""
    ctx = _Consultorio()
    ctx.usuario = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-unicidad-{tenant.slug}@consultorio.test",
        nombre="Dra. Unicidad",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-60150",
        activo=True,
    )
    ctx.paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Camila Unicidad",
        dni=f"3{tenant.slug[-1].upper()}554442",
        telefono="+5491199990000",
        optin_wa=True,
        activo=True,
    )
    ctx.sillon = Sillon(
        id=uuid.uuid4(), tenant_id=tenant.id, nombre=f"Box Unicidad {tenant.slug}", activo=True
    )
    ctx.prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Consulta Unicidad {tenant.slug}",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([ctx.usuario, ctx.paciente, ctx.sillon, ctx.prestacion])
    await session.flush()
    session.add_all(
        [
            CoberturaOS(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                obra_social="OSDE",
                prestacion_id=ctx.prestacion.id,
                arancel=Decimal("30000.00"),
                copago=Decimal("0.00"),
                vigencia_desde=date(2020, 1, 1),
                vigencia_hasta=None,
                activa=True,
            ),
            CoberturaOS(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                obra_social="IOMA",
                prestacion_id=ctx.prestacion.id,
                arancel=Decimal("25000.00"),
                copago=Decimal("0.00"),
                vigencia_desde=date(2020, 1, 1),
                vigencia_hasta=None,
                activa=True,
            ),
        ]
    )
    await session.flush()
    return ctx


async def _turno(session: AsyncSession, tenant: Tenant, ctx: _Consultorio) -> Turno:
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.usuario.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=ctx.prestacion.id,
        inicio=INICIO,
        fin=INICIO + timedelta(minutes=30),
        estado=EstadoTurno.FINALIZADO.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    session.add(turno)
    await session.flush()
    return turno


async def _borrador(
    session: AsyncSession,
    tenant: Tenant,
    ctx: _Consultorio,
    *,
    obra_social: str = "OSDE",
    periodo: str = "202611",
):
    return await generar_borrador(
        session,
        tenant_id=tenant.id,
        datos=LiquidacionOSCreate(obra_social=obra_social, periodo=periodo),
        actor_id=ctx.usuario.id,
    )


def _cabecera(
    tenant: Tenant, ctx: _Consultorio, *, periodo: str, estado: EstadoLiquidacionOS
) -> LiquidacionOS:
    datos: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant.id,
        "obra_social": "OSDE",
        "periodo": periodo,
        "estado": estado.value,
        "total": Decimal("30000.00"),
        "created_by": ctx.usuario.id,
    }
    if estado is EstadoLiquidacionOS.PRESENTADA:
        datos["presentada_por"] = ctx.usuario.id
        datos["presentada_at"] = datetime(2026, 11, 30, 12, 0, tzinfo=UTC)
    return LiquidacionOS(**datos)


def _detalle(
    tenant: Tenant,
    liquidacion: LiquidacionOS,
    *,
    turno_id: uuid.UUID,
    periodo: str,
    vigente: bool = True,
) -> LiquidacionOSDetalle:
    return LiquidacionOSDetalle(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        liquidacion_id=liquidacion.id,
        turno_id=turno_id,
        obra_social=liquidacion.obra_social,
        periodo=periodo,
        monto_reclamado=Decimal("30000.00"),
        arancel_vencido=False,
        vigente=vigente,
    )


async def _cantidad_liquidaciones(session: AsyncSession, tenant: Tenant) -> int:
    return len(
        (await session.execute(select(LiquidacionOS).where(LiquidacionOS.tenant_id == tenant.id)))
        .scalars()
        .all()
    )


async def test_doble_borrador_de_la_misma_os_y_periodo_da_409(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D6: el segundo borrador simultáneo se rechaza antes de tocar la DB."""
    ctx = await _seed(session, tenant_a)
    await _turno(session, tenant_a, ctx)
    await _borrador(session, tenant_a, ctx)

    with pytest.raises(Conflicto):
        await _borrador(session, tenant_a, ctx)

    assert await _cantidad_liquidaciones(session, tenant_a) == 1


async def test_un_turno_de_una_liquidacion_presentada_no_entra_en_otra(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """RN-OS-02: el turno de una liquidación `presentada` sigue abierto y bloquea con 409."""
    ctx = await _seed(session, tenant_a)
    turno = await _turno(session, tenant_a, ctx)
    primera = await _borrador(session, tenant_a, ctx)
    await presentar_liquidacion(
        session, tenant_id=tenant_a.id, liquidacion_id=primera.id, actor_id=ctx.usuario.id
    )

    with pytest.raises(Conflicto):
        await _borrador(session, tenant_a, ctx)

    detalles = (
        (
            await session.execute(
                select(LiquidacionOSDetalle).where(
                    LiquidacionOSDetalle.tenant_id == tenant_a.id,
                    LiquidacionOSDetalle.turno_id == turno.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(detalles) == 1
    assert await _cantidad_liquidaciones(session, tenant_a) == 1


async def test_el_mismo_turno_en_obras_sociales_distintas_se_permite(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D3: la unicidad es por OS/período, así que OSDE e IOMA pueden liquidar el mismo turno."""
    ctx = await _seed(session, tenant_a)
    turno = await _turno(session, tenant_a, ctx)

    osde = await _borrador(session, tenant_a, ctx, obra_social="OSDE")
    ioma = await _borrador(session, tenant_a, ctx, obra_social="IOMA")

    assert {detalle.turno_id for detalle in osde.detalles} == {turno.id}
    assert {detalle.turno_id for detalle in ioma.detalles} == {turno.id}
    assert osde.total == Decimal("30000.00")
    assert ioma.total == Decimal("25000.00")


async def test_el_mismo_turno_en_periodos_distintos_se_permite(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D3: el índice parcial incluye el período; dos filas abiertas de distinto período conviven."""
    ctx = await _seed(session, tenant_a)
    turno = await _turno(session, tenant_a, ctx)
    de_octubre = _cabecera(tenant_a, ctx, periodo="202610", estado=EstadoLiquidacionOS.BORRADOR)
    de_noviembre = _cabecera(tenant_a, ctx, periodo="202611", estado=EstadoLiquidacionOS.BORRADOR)
    session.add_all([de_octubre, de_noviembre])
    await session.flush()
    session.add_all(
        [
            _detalle(tenant_a, de_octubre, turno_id=turno.id, periodo="202610"),
            _detalle(tenant_a, de_noviembre, turno_id=turno.id, periodo="202611"),
        ]
    )

    await session.flush()

    abiertos = (
        (
            await session.execute(
                select(LiquidacionOSDetalle).where(
                    LiquidacionOSDetalle.tenant_id == tenant_a.id,
                    LiquidacionOSDetalle.turno_id == turno.id,
                    LiquidacionOSDetalle.vigente.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    assert {fila.periodo for fila in abiertos} == {"202610", "202611"}


async def test_tras_anular_el_turno_vuelve_a_entrar_en_una_nueva_liquidacion(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """RN-OS-02/D3: la baja lógica deja `vigente = false` y libera el turno."""
    ctx = await _seed(session, tenant_a)
    turno = await _turno(session, tenant_a, ctx)
    primera = await _borrador(session, tenant_a, ctx)
    await anular_liquidacion(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=primera.id,
        datos=LiquidacionOSAnularInput(motivo="Se liquidó por error"),
        actor_id=ctx.usuario.id,
    )

    segunda = await _borrador(session, tenant_a, ctx)

    assert segunda.id != primera.id
    assert {detalle.turno_id for detalle in segunda.detalles} == {turno.id}
    assert all(detalle.vigente is True for detalle in segunda.detalles)
    filas = (
        (
            await session.execute(
                select(LiquidacionOSDetalle).where(
                    LiquidacionOSDetalle.tenant_id == tenant_a.id,
                    LiquidacionOSDetalle.turno_id == turno.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(filas) == 2
    assert {fila.vigente for fila in filas} == {True, False}


async def test_insercion_directa_duplicada_lanza_integrity_error(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D3: sin pasar por el caso de uso, el índice parcial rechaza el turno ya abierto."""
    ctx = await _seed(session, tenant_a)
    turno = await _turno(session, tenant_a, ctx)
    borrador = _cabecera(tenant_a, ctx, periodo="202611", estado=EstadoLiquidacionOS.BORRADOR)
    presentada = _cabecera(tenant_a, ctx, periodo="202611", estado=EstadoLiquidacionOS.PRESENTADA)
    session.add_all([borrador, presentada])
    await session.flush()
    session.add(_detalle(tenant_a, borrador, turno_id=turno.id, periodo="202611"))
    await session.flush()

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(_detalle(tenant_a, presentada, turno_id=turno.id, periodo="202611"))
            await session.flush()
