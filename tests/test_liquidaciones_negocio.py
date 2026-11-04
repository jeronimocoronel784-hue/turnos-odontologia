"""Casos de uso de liquidaciones a obras sociales (C-13, tareas 3.1 y 3.2 + Bloque E).

Cubre, con el glosario de `05_reglas_de_negocio.md` y `07_flujos_principales.md`:
1. Alta del borrador: sólo turnos `finalizado` del período con convenio de la OS, cobertura
   resuelta en servidor y marca de arancel vencido congelada (RN-OS-01, RN-OS-02, D2, D5).
2. Unicidad del borrador por OS/período y aislamiento por tenant (D6, R4).
3. Registro de débitos: motivo obligatorio en cada recorte, totales recalculados en servidor y
   evento de auditoría sin datos personales (US-041, R8, RN-SE-01, R9).
4. Bloque E: reclamo único por OS/período (D9), total desde el detalle persistido (D10),
   serialización de las mutaciones (D11) y persistencia de la cabecera (D12).
"""

import asyncio
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas_liquidaciones import (
    LiquidacionOSCreate,
    LiquidacionOSDebitosInput,
    LiquidacionOSDetalleDebitoInput,
    ResultadoOSInput,
)
from app.application.liquidaciones import (
    TIENE_TURNOS_SIN_COBERTURA,
    generar_borrador,
    listar_liquidaciones,
    obtener_liquidacion,
    presentar_liquidacion,
    registrar_debitos,
    registrar_resultado,
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
from app.shared.database import create_engine_for
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


# ---------------------------------------------------------------------------
# Bloque E: reclamo único, total desde el detalle y serialización (D9/D10/D11)
# ---------------------------------------------------------------------------


async def test_el_borrador_informa_los_turnos_ya_reclamados_en_las_advertencias(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D9: el borrador deja afuera los turnos ya reclamados y avisa cuáles son."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    primera = await _borrador(session, tenant_a, ctx)
    await presentar_liquidacion(
        session, tenant_id=tenant_a.id, liquidacion_id=primera.id, actor_id=ctx.usuario.id
    )
    await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=primera.id,
        datos=ResultadoOSInput(
            resultado="pagada",
            detalles=[
                {
                    "turno_id": primera.detalles[0].turno_id,
                    "monto_reconocido": "30000.00",
                }
            ],
        ),
        actor_id=ctx.usuario.id,
    )
    ya_reclamado = primera.detalles[0].turno_id

    # Turno finalizado más tarde: es el único reclamable en la complementaria.
    nuevo = await _crear_turno(
        session, tenant_a, ctx, inicio=datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    )

    complementaria = await _borrador(session, tenant_a, ctx)

    assert [detalle.turno_id for detalle in complementaria.detalles] == [nuevo.id]
    assert complementaria.total == Decimal("30000.00")
    assert any(str(ya_reclamado) in aviso for aviso in complementaria.advertencias), (
        "las advertencias tienen que informar el turno excluido"
    )


async def test_el_total_reconocido_no_depende_del_payload(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R8/D10: el total reconocido es la suma del detalle persistido, no la del payload."""
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

    detalles = list(
        (
            await session.execute(
                select(LiquidacionOSDetalle).where(
                    LiquidacionOSDetalle.liquidacion_id == borrador.id
                )
            )
        )
        .scalars()
        .all()
    )
    suma_persistida = sum(
        (
            _dec(detalle.monto_reconocido)
            for detalle in detalles
            if detalle.monto_reconocido is not None
        ),
        Decimal("0.00"),
    )
    assert actualizado.total_reconocido == suma_persistida == Decimal("15000.00")
    # El turno sin débito no suma: el total no sale de sumar lo que vino en el payload.
    assert actualizado.total == Decimal("60000.00")
    assert actualizado.saldo_debito == Decimal("45000.00")

    # Un total en el payload se rechaza en el borde (`extra='forbid'`).
    with pytest.raises(ValidationError):
        LiquidacionOSDebitosInput.model_validate(
            {
                "detalles": [
                    {
                        "turno_id": str(borrador.detalles[0].turno_id),
                        "monto_reconocido": "15000.00",
                    }
                ],
                "total_reconocido": "999999.00",
            }
        )


async def test_la_edicion_concurrente_del_borrador_no_pisa_el_detalle(
    session: AsyncSession, tenant_a: Tenant, db_url: str, dialecto: str
) -> None:
    """D11: la segunda edición concurrente recibe 409 y no pisa los montos de la primera."""
    if dialecto != "postgresql":
        pytest.skip("el lock pesimista de cabecera sólo lo aplica Postgres")

    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)
    await session.commit()

    engine = create_engine_for(db_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as otra:
        # La transacción principal registra el débito y toma el lock de cabecera.
        await registrar_debitos(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=borrador.id,
            datos=LiquidacionOSDebitosInput(
                detalles=[
                    LiquidacionOSDetalleDebitoInput(
                        turno_id=borrador.detalles[0].turno_id,
                        monto_reconocido=Decimal("15000.00"),
                        debito_motivo="Primer pase",
                    )
                ]
            ),
            actor_id=ctx.usuario.id,
        )
        # La otra transacción intenta pisar el mismo detalle: queda esperando el lock.
        tarea = asyncio.create_task(
            registrar_debitos(
                otra,
                tenant_id=tenant_a.id,
                liquidacion_id=borrador.id,
                datos=LiquidacionOSDebitosInput(
                    detalles=[
                        LiquidacionOSDetalleDebitoInput(
                            turno_id=borrador.detalles[0].turno_id,
                            monto_reconocido=Decimal("10000.00"),
                            debito_motivo="Segundo pase",
                        )
                    ]
                ),
                actor_id=ctx.usuario.id,
            )
        )
        await asyncio.sleep(0.3)
        assert not tarea.done(), "la edición concurrente tiene que quedar esperando el lock"
        await session.commit()

        with pytest.raises(Conflicto):
            await asyncio.wait_for(tarea, timeout=15)

    detalle = (
        await session.execute(
            select(LiquidacionOSDetalle).where(LiquidacionOSDetalle.liquidacion_id == borrador.id)
        )
    ).scalar_one()
    assert _dec(detalle.monto_reconocido) == Decimal("15000.00")
    assert detalle.debito_motivo == "Primer pase"


async def test_el_alta_persiste_la_cabecera_con_turnos_sin_cobertura(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D12/E.9: el conteo de turnos sin cobertura queda persistido en la cabecera."""
    if not TIENE_TURNOS_SIN_COBERTURA:
        pytest.skip("la columna `turnos_sin_cobertura` la agrega la migración correctiva 013")

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

    assert borrador.turnos_sin_cobertura == 1
    cabecera = (
        await session.execute(select(LiquidacionOS).where(LiquidacionOS.id == borrador.id))
    ).scalar_one()
    assert cabecera.turnos_sin_cobertura == 1


# ---------------------------------------------------------------------------
# Bloque E: bordes del período (E.12, D5)
# ---------------------------------------------------------------------------


async def test_el_turno_del_primer_dia_del_periodo_entra_al_borrador(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D5: el rango es semiabierto, así que el 01/11 a las 00:00 UTC entra en noviembre."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 1, 0, 0, tzinfo=UTC))

    borrador = await _borrador(session, tenant_a, ctx)

    assert len(borrador.detalles) == 1
    assert borrador.detalles[0].fecha_turno == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    assert borrador.total == Decimal("30000.00")


async def test_el_turno_del_inicio_del_periodo_siguiente_queda_fuera(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D5: el 01/12 a las 00:00 UTC ya es del período siguiente y no entra en noviembre."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 1, 0, 0, tzinfo=UTC))
    siguiente = await _crear_turno(
        session, tenant_a, ctx, inicio=datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
    )

    borrador = await _borrador(session, tenant_a, ctx)

    assert [detalle.turno_id for detalle in borrador.detalles] != [siguiente.id]
    assert all(detalle.fecha_turno.month == 11 for detalle in borrador.detalles)
    assert len(borrador.detalles) == 1


# ---------------------------------------------------------------------------
# Bloque E: calidad del listado, sin N+1 (E.10, N1)
# ---------------------------------------------------------------------------


async def _contar_selects(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Cuenta los `SELECT` que dispara `listar_liquidaciones` (N1: el lote no escala)."""
    motor = session.get_bind()
    selects: list[str] = []

    def _contar(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(motor, "before_cursor_execute", _contar)
    try:
        await listar_liquidaciones(session, tenant_id=tenant_id)
    finally:
        event.remove(motor, "before_cursor_execute", _contar)
    return len(selects)


async def test_el_listado_no_hace_n_plus_1(session: AsyncSession, tenant_a: Tenant) -> None:
    """N1: el listado carga el lote con un número constante de consultas, no una por item."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 10, 10, 9, 0, tzinfo=UTC))
    await _borrador(session, tenant_a, ctx, periodo="202610")

    con_una = await _contar_selects(session, tenant_a.id)

    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 10, 9, 0, tzinfo=UTC))
    await _borrador(session, tenant_a, ctx, periodo="202611")
    await _crear_turno(session, tenant_a, ctx, inicio=datetime(2026, 12, 10, 9, 0, tzinfo=UTC))
    await _borrador(session, tenant_a, ctx, periodo="202612")

    con_tres = await _contar_selects(session, tenant_a.id)

    assert con_tres == con_una, (
        "el número de consultas del listado no puede crecer con la cantidad de liquidaciones"
    )
    assert con_una <= 6, "el listado tiene que cargar el lote con pocas consultas fijas"


# ---------------------------------------------------------------------------
# Bloque E: guard de PHI en textos libres (E.11, N4, R9)
# ---------------------------------------------------------------------------


async def test_el_debito_con_dni_en_el_motivo_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R9: un motivo que parece un DNI se rechaza con 422 y el detalle queda intacto."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)

    with pytest.raises(EntidadInvalida) as error:
        await registrar_debitos(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=borrador.id,
            datos=LiquidacionOSDebitosInput(
                detalles=[
                    LiquidacionOSDetalleDebitoInput(
                        turno_id=borrador.detalles[0].turno_id,
                        monto_reconocido=Decimal("15000.00"),
                        debito_motivo="Ajuste según DNI 12345678",
                    )
                ]
            ),
            actor_id=ctx.usuario.id,
        )

    mensaje = str(error.value)
    assert "datos personales" in mensaje
    assert "12345678" not in mensaje, "el mensaje de error no puede repetir el dato (R9)"

    detalle = (
        await session.execute(
            select(LiquidacionOSDetalle).where(LiquidacionOSDetalle.liquidacion_id == borrador.id)
        )
    ).scalar_one()
    assert detalle.monto_reconocido is None
    assert detalle.debito_motivo is None

    # Triangulación: el motivo legítimo del negocio no cae en el guard.
    aceptado = await registrar_debitos(
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
    assert aceptado.detalles[0].debito_motivo == "Arancel fuera de nomenclador"


async def test_las_observaciones_con_telefono_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R9: unas observaciones con un teléfono se rechazan con 422 y sin filtrar el dato."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)

    with pytest.raises(EntidadInvalida) as error:
        await registrar_debitos(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=borrador.id,
            datos=LiquidacionOSDebitosInput(
                observaciones="Avisar al +5491144445555",
                detalles=[
                    LiquidacionOSDetalleDebitoInput(
                        turno_id=borrador.detalles[0].turno_id,
                        monto_reconocido=Decimal("15000.00"),
                        debito_motivo="Arancel fuera de nomenclador",
                    )
                ],
            ),
            actor_id=ctx.usuario.id,
        )

    mensaje = str(error.value)
    assert "datos personales" in mensaje
    assert "5491144445555" not in mensaje, "el mensaje de error no puede repetir el dato (R9)"

    cabecera = (
        await session.execute(select(LiquidacionOS).where(LiquidacionOS.id == borrador.id))
    ).scalar_one()
    assert cabecera.observaciones is None


async def test_las_observaciones_quedan_auditadas(session: AsyncSession, tenant_a: Tenant) -> None:
    """N4: las observaciones entran en el snapshot append-only de la auditoría."""
    ctx = await _seed_consultorio(session, tenant_a)
    await _crear_turno(session, tenant_a, ctx)
    borrador = await _borrador(session, tenant_a, ctx)

    await registrar_debitos(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=borrador.id,
        datos=LiquidacionOSDebitosInput(
            observaciones="Nomenclador 2026 sin cobertura",
            detalles=[
                LiquidacionOSDetalleDebitoInput(
                    turno_id=borrador.detalles[0].turno_id,
                    monto_reconocido=Decimal("15000.00"),
                    debito_motivo="Arancel fuera de nomenclador",
                )
            ],
        ),
        actor_id=ctx.usuario.id,
    )

    eventos = (
        (await session.execute(select(Auditoria).where(Auditoria.accion == "liquidacion.debitos")))
        .scalars()
        .all()
    )
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.antes is not None
    assert evento.antes["observaciones"] is None
    assert evento.despues is not None
    assert evento.despues["observaciones"] == "Nomenclador 2026 sin cobertura"
    payload = json.dumps([evento.antes, evento.despues], default=str)
    assert ctx.paciente.dni not in payload
    assert ctx.paciente.telefono not in payload
