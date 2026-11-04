"""Unicidad del reclamo del turno en liquidaciones (`RN-OS-02`, C-13 tarea 3.5 + Bloque E).

Verifica la garantía en las dos capas exigidas por el design (D3/D6/D9):
1. Caso de uso: 409 al repetir el borrador por OS/período y exclusión de los turnos ya
   reclamados por esa obra social y período (mientras la liquidación no esté `anulada`).
2. Base de datos: el índice único parcial `uq_liquidacion_detalle_turno_reclamado` bloquea
   el reclamo duplicado del turno, deja convivir OS/períodos distintos y **sólo la
   anulación** libera el turno (pagarlo no lo libera: el reclamo es un hecho económico,
   D9).
3. Bloque E (D11): dos altas simultáneas dejan un solo borrador y la perdedora recibe 409.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas_liquidaciones import (
    LiquidacionOSAnularInput,
    LiquidacionOSCreate,
    ResultadoOSInput,
)
from app.application.liquidaciones import (
    anular_liquidacion,
    generar_borrador,
    presentar_liquidacion,
    registrar_resultado,
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
from app.shared.database import create_engine_for
from app.shared.exceptions import Conflicto, EntidadInvalida

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


async def _turno(
    session: AsyncSession, tenant: Tenant, ctx: _Consultorio, *, hora: int = 9
) -> Turno:
    inicio = datetime(2026, 11, 10, hora, 0, tzinfo=UTC)
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.usuario.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=ctx.prestacion.id,
        inicio=inicio,
        fin=inicio + timedelta(minutes=30),
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
    """RN-OS-02/D9: el turno de una liquidación `presentada` queda fuera de la complementaria."""
    ctx = await _seed(session, tenant_a)
    turno = await _turno(session, tenant_a, ctx)
    primera = await _borrador(session, tenant_a, ctx)
    await presentar_liquidacion(
        session, tenant_id=tenant_a.id, liquidacion_id=primera.id, actor_id=ctx.usuario.id
    )

    # No quedan turnos nuevos: el alta se rechaza con 422 y no se duplica el turno.
    with pytest.raises(EntidadInvalida):
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


# ---------------------------------------------------------------------------
# Bloque E: reclamo único por obra social y período (D9)
# ---------------------------------------------------------------------------


async def _liquidacion_pagada(
    session: AsyncSession, tenant: Tenant, ctx: _Consultorio
) -> LiquidacionOS:
    """Arma una liquidación pagada (presentada + resultado que reconoce el total)."""
    borrador = await _borrador(session, tenant, ctx)
    await presentar_liquidacion(
        session, tenant_id=tenant.id, liquidacion_id=borrador.id, actor_id=ctx.usuario.id
    )
    await registrar_resultado(
        session,
        tenant_id=tenant.id,
        liquidacion_id=borrador.id,
        datos=ResultadoOSInput(
            resultado="pagada",
            detalles=[
                {
                    "turno_id": borrador.detalles[0].turno_id,
                    "monto_reconocido": "30000.00",
                }
            ],
        ),
        actor_id=ctx.usuario.id,
    )
    return borrador


async def test_el_turno_pagado_no_entra_en_una_liquidacion_complementaria(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D9: un turno ya cobrado no se vuelve a reclamar en la complementaria."""
    ctx = await _seed(session, tenant_a)
    await _turno(session, tenant_a, ctx, hora=9)
    pagada = await _liquidacion_pagada(session, tenant_a, ctx)
    ya_cobrado = pagada.detalles[0].turno_id

    # Un turno finalizado más tarde sí es reclamable.
    nuevo = await _turno(session, tenant_a, ctx, hora=11)

    complementaria = await _borrador(session, tenant_a, ctx)

    assert [detalle.turno_id for detalle in complementaria.detalles] == [nuevo.id]
    assert complementaria.total == Decimal("30000.00")
    assert any(str(ya_cobrado) in aviso for aviso in complementaria.advertencias)


async def test_la_complementaria_sin_turnos_nuevos_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D9: si el período ya está reclamar todo, la complementaria se rechaza con 422."""
    ctx = await _seed(session, tenant_a)
    await _turno(session, tenant_a, ctx, hora=9)
    await _liquidacion_pagada(session, tenant_a, ctx)

    with pytest.raises(EntidadInvalida) as error:
        await _borrador(session, tenant_a, ctx)

    assert "no hay turnos nuevos para liquidar en ese período" in str(error.value)
    assert await _cantidad_liquidaciones(session, tenant_a) == 1


async def test_la_anulacion_libera_el_reclamo_del_turno(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D9: sólo la anulación (baja lógica) libera el turno ya reclamado."""
    ctx = await _seed(session, tenant_a)
    turno = await _turno(session, tenant_a, ctx, hora=9)
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
    assert [detalle.turno_id for detalle in segunda.detalles] == [turno.id]


async def test_la_carrera_de_dos_altas_devuelve_409_y_un_solo_borrador(
    session: AsyncSession, tenant_a: Tenant, db_url: str, dialecto: str
) -> None:
    """D11: dos altas simultáneas dejan un solo borrador y la perdedora recibe 409."""
    if dialecto != "postgresql":
        pytest.skip("la carrera contra el índice único requiere Postgres")

    ctx = await _seed(session, tenant_a)
    await _turno(session, tenant_a, ctx, hora=9)
    await session.commit()

    engine = create_engine_for(db_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as primera, maker() as segunda:
        tareas = [
            asyncio.create_task(
                generar_borrador(
                    sesion,
                    tenant_id=tenant_a.id,
                    datos=LiquidacionOSCreate(obra_social="OSDE", periodo="202611"),
                    actor_id=ctx.usuario.id,
                )
            )
            for sesion in (primera, segunda)
        ]
        hechos, _ = await asyncio.wait(tareas, timeout=20, return_when=asyncio.FIRST_COMPLETED)
        assert len(hechos) == 1
        ganadora = tareas[0] if tareas[0] in hechos else tareas[1]
        perdedora = tareas[1] if tareas[0] in hechos else tareas[0]
        # La ganadora confirma: la perdedora choca contra el índice y se traduce a 409.
        await (primera if ganadora is tareas[0] else segunda).commit()

        with pytest.raises(Conflicto):
            await asyncio.wait_for(perdedora, timeout=20)

    assert await _cantidad_liquidaciones(session, tenant_a) == 1
