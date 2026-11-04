"""Casos de uso de liquidaciones a obras sociales (C-13, tareas 3.1 y 3.2).

Cubre, con el glosario de `05_reglas_de_negocio.md` y `07_flujos_principales.md`:
1. Alta del borrador: sólo turnos `finalizado` del período con convenio de la OS, cobertura
   resuelta en servidor y marca de arancel vencido congelada (RN-OS-01, RN-OS-02, D2, D5).
2. Unicidad del borrador por OS/período y aislamiento por tenant (D6, R4).
3. Registro de débitos: motivo obligatorio en cada recorte, totales recalculados en servidor y
   evento de auditoría sin datos personales (US-041, R8, RN-SE-01, R9).
"""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_liquidaciones import (
    LiquidacionOSCreate,
    LiquidacionOSDebitosInput,
    LiquidacionOSDetalleDebitoInput,
)
from app.application.liquidaciones import (
    generar_borrador,
    obtener_liquidacion,
    registrar_debitos,
)
from app.domain.auditoria import Auditoria
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
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

CERO = Decimal("0.00")
INICIO_NOVIEMBRE = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def _dec(valor: object) -> Decimal:
    """Normaliza montos leídos del ORM (SQLite devuelve float) a `Decimal` de 2 decimales."""
    return Decimal(str(valor)).quantize(Decimal("0.01"))


class _Consultorio:
    """Contexto mínimo para liquidar: profesional, paciente, sillón, prestaciones y convenios."""

    def __init__(self) -> None:
        self.usuario: Usuario
        self.paciente: Paciente
        self.sillon: Sillon
        self.prestacion_osde: Prestacion
        self.prestacion_sin_convenio: Prestacion
        self.prestacion_vencida: Prestacion


async def _seed_consultorio(session: AsyncSession, tenant: Tenant) -> _Consultorio:
    """Crea el consultorio con una prestación con convenio, una sin convenio y una vencida."""
    ctx = _Consultorio()
    ctx.usuario = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-liquidaciones-{tenant.slug}@consultorio.test",
        nombre="Dra. Liquidaciones",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-60130",
        activo=True,
    )
    ctx.paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Valentina Liquidación",
        dni=f"3{tenant.slug[-1].upper()}554440",
        telefono="+5491177778888",
        optin_wa=True,
        activo=True,
    )
    ctx.sillon = Sillon(
        id=uuid.uuid4(), tenant_id=tenant.id, nombre=f"Box OS {tenant.slug}", activo=True
    )
    ctx.prestacion_osde = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Consulta OSDE {tenant.slug}",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    ctx.prestacion_sin_convenio = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Consulta particular {tenant.slug}",
        duracion_min=30,
        precio_particular=Decimal("15000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    ctx.prestacion_vencida = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Consulta con arancel vencido {tenant.slug}",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all(
        [
            ctx.usuario,
            ctx.paciente,
            ctx.sillon,
            ctx.prestacion_osde,
            ctx.prestacion_sin_convenio,
            ctx.prestacion_vencida,
        ]
    )
    await session.flush()
    session.add_all(
        [
            CoberturaOS(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                obra_social="OSDE",
                prestacion_id=ctx.prestacion_osde.id,
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
                prestacion_id=ctx.prestacion_osde.id,
                arancel=Decimal("25000.00"),
                copago=Decimal("0.00"),
                vigencia_desde=date(2020, 1, 1),
                vigencia_hasta=None,
                activa=True,
            ),
            CoberturaOS(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                obra_social="OSDE",
                prestacion_id=ctx.prestacion_vencida.id,
                arancel=Decimal("30000.00"),
                copago=Decimal("0.00"),
                vigencia_desde=date(2020, 1, 1),
                vigencia_hasta=date(2026, 10, 31),
                activa=True,
            ),
        ]
    )
    await session.flush()
    return ctx


async def _crear_turno(
    session: AsyncSession,
    tenant: Tenant,
    ctx: _Consultorio,
    *,
    inicio: datetime = INICIO_NOVIEMBRE,
    estado: EstadoTurno = EstadoTurno.FINALIZADO,
    prestacion: Prestacion | None = None,
) -> Turno:
    """Crea un turno con el estado pedido (los finalizados son los únicos liquidables)."""
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.usuario.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=(prestacion or ctx.prestacion_osde).id,
        inicio=inicio,
        fin=inicio + timedelta(minutes=30),
        estado=estado.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    session.add(turno)
    await session.flush()
    return turno


def _alta(obra_social: str = "OSDE", periodo: str = "202611") -> LiquidacionOSCreate:
    return LiquidacionOSCreate(obra_social=obra_social, periodo=periodo)


async def _borrador(
    session: AsyncSession,
    tenant: Tenant,
    ctx: _Consultorio,
    *,
    periodo: str = "202611",
    obra_social: str = "OSDE",
):
    """Genera un borrador con el consultorio ya sembrado."""
    return await generar_borrador(
        session,
        tenant_id=tenant.id,
        datos=_alta(obra_social, periodo),
        actor_id=ctx.usuario.id,
    )


async def _marcar_presentada(
    session: AsyncSession, tenant: Tenant, ctx: _Consultorio, liquidacion_id: uuid.UUID
) -> LiquidacionOS:
    """Deja la cabecera en `presentada` a nivel ORM (setup de tests de débitos y anulación)."""
    liquidacion = await obtener_liquidacion(
        session, tenant_id=tenant.id, liquidacion_id=liquidacion_id
    )
    liquidacion.estado = EstadoLiquidacionOS.PRESENTADA.value
    liquidacion.presentada_por = ctx.usuario.id
    liquidacion.presentada_at = datetime(2026, 11, 30, 12, 0, tzinfo=UTC)
    await session.flush()
    return liquidacion


# ---------------------------------------------------------------------------
# 3.1 Alta del borrador (RN-OS-02, D5)
# ---------------------------------------------------------------------------


async def test_borrador_incluye_solo_los_finalizados_del_periodo(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D5: tres finalizados de noviembre entran; octubre y diciembre quedan afuera."""
    ctx = await _seed_consultorio(session, tenant_a)
    for hora in (9, 11, 15):
        await _crear_turno(
            session, tenant_a, ctx, inicio=datetime(2026, 11, 10, hora, 0, tzinfo=UTC)
        )
    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 12, 1, 9, 0, tzinfo=UTC))

    borrador = await _borrador(session, tenant_a, ctx)

    assert borrador.estado is EstadoLiquidacionOS.BORRADOR
    assert len(borrador.detalles) == 3
    assert borrador.total == Decimal("90000.00")
    assert {detalle.monto_reclamado for detalle in borrador.detalles} == {Decimal("30000.00")}
    assert {detalle.fecha_turno.month for detalle in borrador.detalles} == {11}
    assert borrador.turnos_sin_cobertura == 0


@pytest.mark.parametrize(
    "estado",
    [
        EstadoTurno.PENDIENTE,
        EstadoTurno.CONFIRMADO,
        EstadoTurno.PRESENTE,
        EstadoTurno.CANCELADO,
        EstadoTurno.AUSENTE,
        EstadoTurno.REPROGRAMADO,
    ],
)
async def test_borrador_excluye_turnos_no_finalizados(
    session: AsyncSession, tenant_a: Tenant, estado: EstadoTurno
) -> None:
    """RN-OS-02: sólo `finalizado` es liquidable; los otros seis estados quedan afuera."""
    ctx = await _seed_consultorio(session, tenant_a)
    finalizado = await _crear_turno(session, tenant_a, ctx)
    otro = await _crear_turno(
        session,
        tenant_a,
        ctx,
        inicio=datetime(2026, 11, 10, 11, 0, tzinfo=UTC),
        estado=estado,
    )

    borrador = await _borrador(session, tenant_a, ctx)

    turnos = {detalle.turno_id for detalle in borrador.detalles}
    assert turnos == {finalizado.id}
    assert otro.id not in turnos


async def test_borrador_registra_auditoria_del_alta_sin_phi(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """RN-SE-01 / R9: el alta deja un evento append-only con montos y sin datos del paciente."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno(session, tenant_a, ctx)

    borrador = await _borrador(session, tenant_a, ctx)

    eventos = list(
        (await session.execute(select(Auditoria).where(Auditoria.accion == "liquidacion.crear")))
        .scalars()
        .all()
    )
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.tenant_id == tenant_a.id
    assert evento.actor_id == ctx.usuario.id
    assert evento.entidad == "liquidacion_os"
    assert evento.entidad_id == str(borrador.id)
    assert evento.antes is None
    assert evento.despues is not None
    assert evento.despues["estado"] == "borrador"
    assert evento.despues["total"] == "30000.00"
    assert evento.despues["turnos"] == 1
    payload = json.dumps(evento.despues, ensure_ascii=False)
    assert str(turno.id) not in payload
    assert ctx.paciente.dni not in payload
    assert ctx.paciente.telefono not in payload


async def test_borrador_informa_los_turnos_sin_cobertura(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """RN-OS-01: el turno sin convenio queda afuera y se informa cuántos no tienen cobertura."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    await _crear_turno(
        session,
        tenant_a,
        ctx,
        inicio=datetime(2026, 11, 10, 11, 0, tzinfo=UTC),
        prestacion=ctx.prestacion_sin_convenio,
    )

    borrador = await _borrador(session, tenant_a, ctx)

    assert len(borrador.detalles) == 1
    assert borrador.turnos_sin_cobertura == 1
    assert borrador.total == Decimal("30000.00")


async def test_borrador_sin_turnos_con_cobertura_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D5: un período sin turnos finalizados con convenio no genera un borrador vacío."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(
        session,
        tenant_a,
        ctx,
        prestacion=ctx.prestacion_sin_convenio,
    )

    with pytest.raises(EntidadInvalida):
        await _borrador(session, tenant_a, ctx)

    existentes = (
        (await session.execute(select(LiquidacionOS).where(LiquidacionOS.tenant_id == tenant_a.id)))
        .scalars()
        .all()
    )
    assert existentes == []


async def test_borrador_congela_arancel_vencido_con_advertencia(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D2: el arancel vencido se usa con advertencia y la marca queda en el detalle."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx, prestacion=ctx.prestacion_vencida)

    borrador = await _borrador(session, tenant_a, ctx)

    assert len(borrador.detalles) == 1
    assert borrador.detalles[0].arancel_vencido is True
    assert borrador.detalles[0].monto_reclamado == Decimal("30000.00")
    assert borrador.advertencias
    assert "venció" in borrador.advertencias[0].lower()


async def test_segundo_borrador_misma_os_y_periodo_da_409(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D6: un solo borrador simultáneo por OS/período, comparando la OS sin mayúsculas."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    await _borrador(session, tenant_a, ctx)

    with pytest.raises(Conflicto):
        await _borrador(session, tenant_a, ctx, obra_social="osde")

    assert (
        len(
            (
                await session.execute(
                    select(LiquidacionOS).where(
                        LiquidacionOS.tenant_id == tenant_a.id,
                        LiquidacionOS.estado == EstadoLiquidacionOS.BORRADOR.value,
                    )
                )
            )
            .scalars()
            .all()
        )
        == 1
    )


async def test_borrador_no_mezcla_turnos_de_otro_tenant(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """R4: los turnos del consultorio B no aparecen en la liquidación del consultorio A."""
    ctx_b = await _seed_consultorio(session, tenant_b)
    await _crear_turno(session, tenant_b, ctx_b)

    ctx_a = await _seed_consultorio(session, tenant_a)
    with pytest.raises(EntidadInvalida):
        await _borrador(session, tenant_a, ctx_a)

    borrador_b = await _borrador(session, tenant_b, ctx_b)
    assert len(borrador_b.detalles) == 1


async def test_liquidacion_de_otro_tenant_da_404(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """R4: pedir una liquidación de otro consultorio responde 404, sin filtrar su existencia."""
    ctx_b = await _seed_consultorio(session, tenant_b)
    await _crear_turno(session, tenant_b, ctx_b)
    borrador_b = await _borrador(session, tenant_b, ctx_b)

    await _seed_consultorio(session, tenant_a)
    with pytest.raises(NoEncontrado):
        await obtener_liquidacion(session, tenant_id=tenant_a.id, liquidacion_id=borrador_b.id)

    assert (
        await obtener_liquidacion(session, tenant_id=tenant_b.id, liquidacion_id=borrador_b.id)
    ).id == borrador_b.id


# ---------------------------------------------------------------------------
# 3.2 Registro de débitos (US-041, R8, RN-SE-01)
# ---------------------------------------------------------------------------


def _debito(turno_id: uuid.UUID, monto: str, motivo: str | None = None) -> dict[str, object]:
    datos: dict[str, object] = {"turno_id": turno_id, "monto_reconocido": monto}
    if motivo is not None:
        datos["debito_motivo"] = motivo
    return datos


async def test_debito_con_motivo_actualiza_totales_y_audita_sin_phi(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """US-041: un recorte con motivo baja `total_reconocido` y audita sin datos del paciente."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)

    actualizado = await registrar_debitos(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=borrador.id,
        datos=LiquidacionOSDebitosInput(
            detalles=[
                LiquidacionOSDetalleDebitoInput(
                    turno_id=borrador.detalles[0].turno_id,
                    monto_reconocido=Decimal("15000.00"),
                    debito_motivo="Arancel fuera de nomenclador",
                )
            ]
        ),
        actor_id=ctx.usuario.id,
    )

    assert actualizado.total == Decimal("30000.00")
    assert actualizado.total_reconocido == Decimal("15000.00")
    assert actualizado.detalles[0].monto_reconocido == Decimal("15000.00")
    assert actualizado.detalles[0].debito_motivo == "Arancel fuera de nomenclador"

    eventos = (
        (await session.execute(select(Auditoria).where(Auditoria.accion == "liquidacion.debitos")))
        .scalars()
        .all()
    )
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.entidad == "liquidacion_os"
    assert evento.entidad_id == str(borrador.id)
    assert evento.actor_id == ctx.usuario.id
    payload = json.dumps([evento.antes, evento.despues], default=str)
    assert "15000.00" in payload
    assert ctx.paciente.dni not in payload
    assert ctx.paciente.telefono not in payload


async def test_debito_parcial_suma_los_reconocidos_del_servidor(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R8: con dos turnos, `total_reconocido` suma lo reconocido y nunca un total del cliente."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 10, 11, 0, tzinfo=UTC))
    borrador = await _borrador(session, tenant_a, ctx)

    actualizado = await registrar_debitos(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=borrador.id,
        datos=LiquidacionOSDebitosInput(
            detalles=[
                LiquidacionOSDetalleDebitoInput(
                    turno_id=borrador.detalles[0].turno_id,
                    monto_reconocido=Decimal("15000.00"),
                    debito_motivo="Débito de la OS",
                )
            ]
        ),
        actor_id=ctx.usuario.id,
    )

    assert actualizado.total == Decimal("60000.00")
    assert actualizado.total_reconocido == Decimal("15000.00")


async def test_debito_sin_motivo_da_422_y_no_cambia_el_detalle(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """US-041: reconocer menos sin motivo se rechaza y el detalle queda intacto."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)

    with pytest.raises(EntidadInvalida):
        await registrar_debitos(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=borrador.id,
            datos=LiquidacionOSDebitosInput(
                detalles=[
                    LiquidacionOSDetalleDebitoInput(
                        turno_id=borrador.detalles[0].turno_id,
                        monto_reconocido=Decimal("15000.00"),
                    )
                ]
            ),
            actor_id=ctx.usuario.id,
        )

    detalle = (
        await session.execute(
            select(LiquidacionOSDetalle).where(
                LiquidacionOSDetalle.turno_id == borrador.detalles[0].turno_id
            )
        )
    ).scalar_one()
    assert detalle.monto_reconocido is None
    assert detalle.debito_motivo is None


async def test_debito_mayor_al_reclamado_da_422(session: AsyncSession, tenant_a: Tenant) -> None:
    """R8: la OS no puede reconocer más de lo reclamado por el turno."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)

    with pytest.raises(EntidadInvalida):
        await registrar_debitos(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=borrador.id,
            datos=LiquidacionOSDebitosInput(
                detalles=[
                    LiquidacionOSDetalleDebitoInput(
                        turno_id=borrador.detalles[0].turno_id,
                        monto_reconocido=Decimal("40000.00"),
                        debito_motivo="Ajuste manual",
                    )
                ]
            ),
            actor_id=ctx.usuario.id,
        )


async def test_debito_de_un_turno_ajeno_da_422(session: AsyncSession, tenant_a: Tenant) -> None:
    """US-041: sólo se debita un turno que forma parte de la liquidación."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)
    ajeno = await _crear_turno(
        session, tenant_a, ctx, inicio=datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    )

    with pytest.raises(EntidadInvalida):
        await registrar_debitos(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=borrador.id,
            datos=LiquidacionOSDebitosInput(detalles=[_debito(ajeno.id, "10000.00", "Ajeno")]),
            actor_id=ctx.usuario.id,
        )


async def test_debitos_sobre_una_liquidacion_presentada_da_409(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """Inmutabilidad del detalle presentado: editar débitos responde 409."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)
    presentada = await _marcar_presentada(session, tenant_a, ctx, borrador.id)

    with pytest.raises(Conflicto):
        await registrar_debitos(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=LiquidacionOSDebitosInput(
                detalles=[
                    LiquidacionOSDetalleDebitoInput(
                        turno_id=borrador.detalles[0].turno_id,
                        monto_reconocido=Decimal("15000.00"),
                        debito_motivo="Tarde",
                    )
                ]
            ),
            actor_id=ctx.usuario.id,
        )

    detalle = (
        await session.execute(
            select(LiquidacionOSDetalle).where(LiquidacionOSDetalle.liquidacion_id == presentada.id)
        )
    ).scalar_one()
    assert detalle.monto_reconocido is None
