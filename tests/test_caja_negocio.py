"""Tests de integración de lógica de negocio de Señas y Caja diaria (tarea 2.1).

Cubre, con el glosario del dominio de `05_reglas_de_negocio.md` y `07_flujos_principales.md`:
1. Auto-generación de la `Sena` al reservar un turno con `requiere_sena` (RN-PA-02, Flujo 1 paso 6).
2. Cobro de la seña: habilita `confirmado`, registra `MovimientoCaja` y se asocia al cierre abierto
   (RN-PA-01, RN-PA-05).
3. Política de cancelación: dentro de término -> `devuelta`; fuera de término o `ausente` ->
   retenida en `aplicada` (RN-PA-04).
4. Vencimiento impago: seña `vencida` + turno `cancelado` + slot liberado + aviso a la lista de
   espera.
5. Liquidación del turno: `saldo = precio - cobertura_os - sena_cobrada` y cobro que aplica la seña
   (Flujo 4, R8).
6. Caja diaria: total sistema, diferencia visible, inmutabilidad del cierre y reapertura auditada
   (RN-PA-05, RN-SE-01).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_caja import (
    CierreCajaAbrirInput,
    CierreCajaCerrarInput,
    CierreCajaReabrirInput,
    CobrarTurnoInput,
    MovimientoCajaCreate,
    SenaCobrarInput,
    SenaCreate,
    SenaResolverCancelacionInput,
)
from app.application.agenda import crear_turno
from app.application.caja import (
    abrir_cierre_caja,
    calcular_liquidacion_turno,
    cerrar_caja,
    cobrar_saldo_turno,
    cobrar_sena,
    crear_sena,
    listar_senas,
    reabrir_caja,
    registrar_movimiento_caja,
    resolver_sena_por_cancelacion,
    vencer_sena_impaga,
)
from app.domain.caja import (
    EstadoCierreCaja,
    EstadoSena,
    MedioPago,
    MovimientoCaja,
    Sena,
    TipoMovimientoCaja,
)
from app.domain.cobertura_os import CoberturaOS
from app.domain.lista_espera import CanalAviso, EstadoListaEspera, ListaEspera
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, Turno
from app.domain.usuario import RolUsuario, Usuario
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

CERO = Decimal("0.00")


def _dec(valor: object) -> Decimal:
    """Normaliza montos leídos del ORM (SQLite devuelve float) a `Decimal` con 2 decimales."""
    return Decimal(str(valor)).quantize(Decimal("0.01"))


class _Consultorio:
    """Contexto mínimo de un consultorio para ejercitar señas y caja."""

    def __init__(self) -> None:
        self.odontologo: Usuario
        self.paciente: Paciente
        self.sillon: Sillon
        self.prestacion_con_sena: Prestacion
        self.prestacion_sin_sena: Prestacion


async def _seed_consultorio(session: AsyncSession, tenant: Tenant) -> _Consultorio:
    """Crea profesional, paciente, sillón, prestaciones y convenio OSDE de referencia."""
    ctx = _Consultorio()
    ctx.odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="odonto-caja-negocio@consultorio.test",
        nombre="Dra. Caja Negocio",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-20201",
        activo=True,
    )
    ctx.paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Sofía Seña",
        dni="40111222",
        telefono="+5491155556666",
        optin_wa=True,
        activo=True,
    )
    ctx.sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Box Caja",
        sucursal="central",
        activo=True,
    )
    ctx.prestacion_con_sena = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Implante con seña",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=True,
        monto_sena=Decimal("10000.00"),
        invasiva=False,
        activa=True,
    )
    ctx.prestacion_sin_sena = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Consulta sin seña",
        duracion_min=30,
        precio_particular=Decimal("15000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    cobertura = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        obra_social="OSDE",
        prestacion_id=ctx.prestacion_con_sena.id,
        arancel=Decimal("20000.00"),
        copago=Decimal("30000.00"),
        vigencia_desde=date(2020, 1, 1),
        vigencia_hasta=None,
        activa=True,
    )
    # Sin `relationship()` el unit-of-work no ordena los INSERTs: los padres
    # (prestaciones) se flushEAN antes que el hijo (cobertura_os) para no violar la FK.
    session.add_all(
        [
            ctx.odontologo,
            ctx.paciente,
            ctx.sillon,
            ctx.prestacion_con_sena,
            ctx.prestacion_sin_sena,
        ]
    )
    await session.flush()
    session.add(cobertura)
    await session.flush()
    return ctx


async def _crear_turno_con_sena(
    session: AsyncSession,
    tenant: Tenant,
    ctx: _Consultorio,
    *,
    inicio: datetime | None = None,
) -> Turno:
    turno, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.odontologo.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=ctx.prestacion_con_sena.id,
        inicio=inicio or datetime(2026, 12, 1, 10, 0, tzinfo=UTC),
        actor_id=ctx.odontologo.id,
    )
    await session.flush()
    return turno


async def _sena_de(session: AsyncSession, turno: Turno) -> Sena:
    sena = (
        await session.execute(select(Sena).where(Sena.turno_id == turno.id))
    ).scalar_one_or_none()
    assert sena is not None
    return sena


# ---------------------------------------------------------------------------
# 1. Auto-generación de la seña al reservar (RN-PA-02)
# ---------------------------------------------------------------------------


async def test_crear_turno_con_prestacion_que_exige_sena_genera_sena_pendiente(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-02: reservar con `requiere_sena` deja una seña `pendiente` por `monto_sena`."""
    ctx = await _seed_consultorio(session, tenant_a)

    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)

    assert sena.tenant_id == tenant_a.id
    assert sena.estado == EstadoSena.PENDIENTE.value
    assert _dec(sena.monto) == Decimal("10000.00")
    assert turno.sena_cobrada is False
    assert sena.vence_at is not None
    horas = (sena.vence_at.replace(tzinfo=UTC) - datetime.now(UTC)).total_seconds() / 3600
    assert Decimal(str(round(horas, 1))) == Decimal("24.0")


async def test_crear_turno_sin_requiere_sena_no_genera_sena(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Edge RN-PA-02: prestación sin seña no genera fila `sena`."""
    ctx = await _seed_consultorio(session, tenant_a)

    turno, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.odontologo.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=ctx.prestacion_sin_sena.id,
        inicio=datetime(2026, 12, 1, 11, 0, tzinfo=UTC),
        actor_id=ctx.odontologo.id,
    )
    await session.flush()

    assert await listar_senas(session, tenant_id=tenant_a.id, turno_id=turno.id) == []


async def test_crear_turno_con_sena_ya_cobrada_no_duplica_sena(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Edge RN-PA-02: un turno reprogramado con seña ya cobrada no genera otra seña pendiente."""
    ctx = await _seed_consultorio(session, tenant_a)

    turno, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.odontologo.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=ctx.prestacion_con_sena.id,
        inicio=datetime(2026, 12, 1, 12, 0, tzinfo=UTC),
        sena_cobrada=True,
        actor_id=ctx.odontologo.id,
    )
    await session.flush()

    assert await listar_senas(session, tenant_id=tenant_a.id, turno_id=turno.id) == []


async def test_crear_sena_manual_calcula_monto_en_servidor_y_rechaza_turno_sin_sena(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """R8: el monto sale de `prestacion.monto_sena`; un turno sin seña exigible se rechaza."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)

    # El turno ya tiene su seña auto-generada: el alta manual duplicada choca (1:1).
    with pytest.raises(Conflicto):
        await crear_sena(
            session,
            tenant_id=tenant_a.id,
            datos=SenaCreate(turno_id=turno.id),
            actor_id=ctx.odontologo.id,
        )

    turno_sin_sena, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.odontologo.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=ctx.prestacion_sin_sena.id,
        inicio=datetime(2026, 12, 1, 13, 0, tzinfo=UTC),
        actor_id=ctx.odontologo.id,
    )
    await session.flush()

    with pytest.raises(EntidadInvalida):
        await crear_sena(
            session,
            tenant_id=tenant_a.id,
            datos=SenaCreate(turno_id=turno_sin_sena.id),
            actor_id=ctx.odontologo.id,
        )


async def test_crear_sena_manual_en_turno_de_otro_tenant_no_lo_encuentra(
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
) -> None:
    """R4: el turno de otro consultorio no existe para el tenant del token (404)."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)

    with pytest.raises(NoEncontrado):
        await crear_sena(
            session,
            tenant_id=tenant_b.id,
            datos=SenaCreate(turno_id=turno.id),
            actor_id=ctx.odontologo.id,
        )


# ---------------------------------------------------------------------------
# 2. Cobro de la seña (RN-PA-01, RN-PA-05)
# ---------------------------------------------------------------------------


async def test_cobrar_sena_habilita_confirmacion_y_registra_ingreso_en_cierre_abierto(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-01/05: el cobro marca `sena_cobrada`, habilita `confirmado` y crea el movimiento."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)

    cierre = await abrir_cierre_caja(
        session,
        tenant_id=tenant_a.id,
        datos=CierreCajaAbrirInput(fecha=date(2026, 12, 1)),
        actor_id=ctx.odontologo.id,
    )

    cobrada = await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    assert cobrada.estado == EstadoSena.COBRADA.value
    assert turno.sena_cobrada is True

    movimiento = (
        await session.execute(select(MovimientoCaja).where(MovimientoCaja.sena_id == sena.id))
    ).scalar_one()
    assert movimiento.tipo == TipoMovimientoCaja.INGRESO.value
    assert movimiento.medio == MedioPago.EFECTIVO.value
    assert _dec(movimiento.monto) == Decimal("10000.00")
    assert movimiento.cierre_id == cierre.id
    assert movimiento.turno_id == turno.id
    assert movimiento.tenant_id == tenant_a.id


async def test_cobrar_sena_dos_veces_es_idempotente_y_no_duplica_movimiento(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """R8: reintentar el cobro de una seña ya `cobrada` no crea un segundo movimiento."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)

    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.DEBITO),
        actor_id=ctx.odontologo.id,
    )
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.DEBITO),
        actor_id=ctx.odontologo.id,
    )

    movimientos = (
        (await session.execute(select(MovimientoCaja).where(MovimientoCaja.sena_id == sena.id)))
        .scalars()
        .all()
    )
    assert len(movimientos) == 1


async def test_cobrar_sena_devuelta_rechaza_transicion_invalida(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Edge RN-PA-01: una seña `devuelta` es terminal, no se puede volver a cobrar."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)

    await resolver_sena_por_cancelacion(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaResolverCancelacionInput(motivo="Canceló con anticipación"),
        actor_id=ctx.odontologo.id,
        ahora=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
    )

    with pytest.raises(EntidadInvalida):
        await cobrar_sena(
            session,
            tenant_id=tenant_a.id,
            sena_id=sena.id,
            datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
            actor_id=ctx.odontologo.id,
        )


# ---------------------------------------------------------------------------
# 3. Política de cancelación (RN-PA-04)
# ---------------------------------------------------------------------------


async def test_resolver_cancelacion_en_termino_devuelve_la_sena_cobrada(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-04: cancelación con 24 h o más de anticipación devuelve la seña."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    devuelta = await resolver_sena_por_cancelacion(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaResolverCancelacionInput(motivo="Avisó con 48 h"),
        actor_id=ctx.odontologo.id,
        ahora=datetime(2026, 11, 29, 10, 0, tzinfo=UTC),
    )

    assert devuelta.estado == EstadoSena.DEVUELTA.value
    # RN-PA-04: devolver la seña deja el turno sin seña acreditada.
    assert turno.sena_cobrada is False


@pytest.mark.parametrize(
    ("ahora", "ausente"),
    [
        (datetime(2026, 12, 1, 8, 0, tzinfo=UTC), False),  # 2 h antes: fuera de término
        (datetime(2026, 12, 1, 10, 0, tzinfo=UTC), True),  # inasistencia
    ],
)
async def test_resolver_cancelacion_fuera_de_termino_o_ausente_retiene_la_sena_aplicada(
    session: AsyncSession,
    tenant_a: Tenant,
    ahora: datetime,
    ausente: bool,
) -> None:
    """RN-PA-04: fuera de término o inasistencia, la seña se retiene y se `aplica`."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    aplicada = await resolver_sena_por_cancelacion(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaResolverCancelacionInput(ausente=ausente, motivo="No asistió"),
        actor_id=ctx.odontologo.id,
        ahora=ahora,
    )

    assert aplicada.estado == EstadoSena.APLICADA.value


# ---------------------------------------------------------------------------
# 4. Vencimiento impago (Flujo 1 paso 6)
# ---------------------------------------------------------------------------


async def test_vencer_sena_impaga_cancela_turno_libera_slot_y_avisa_lista_de_espera(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-02: seña vencida impaga cancela el turno, libera el slot y ofrece el hueco."""
    ctx = await _seed_consultorio(session, tenant_a)
    inicio = datetime(2026, 12, 2, 10, 0, tzinfo=UTC)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx, inicio=inicio)
    sena = await _sena_de(session, turno)

    espera = ListaEspera(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=ctx.paciente.id,
        prestacion_id=ctx.prestacion_con_sena.id,
        profesional_id=ctx.odontologo.id,
        prioridad=1,
        estado=EstadoListaEspera.ACTIVA.value,
        canal_aviso=CanalAviso.WA.value,
    )
    session.add(espera)
    await session.flush()

    vencida = await vencer_sena_impaga(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        ahora=datetime(2026, 12, 3, 10, 0, tzinfo=UTC),
    )

    assert vencida.estado == EstadoSena.VENCIDA.value
    assert turno.estado == EstadoTurno.CANCELADO.value
    assert espera.estado == EstadoListaEspera.AVISADA.value

    # El slot quedó libre: el mismo horario y sillón se puede volver a reservar.
    nuevo, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.odontologo.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=ctx.prestacion_con_sena.id,
        inicio=inicio,
        actor_id=ctx.odontologo.id,
    )
    assert nuevo.estado == EstadoTurno.PENDIENTE.value


async def test_vencer_sena_ya_cobrada_rechaza_la_transicion(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Edge: una seña `cobrada` ya no puede vencer."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    with pytest.raises(EntidadInvalida):
        await vencer_sena_impaga(
            session,
            tenant_id=tenant_a.id,
            sena_id=sena.id,
            ahora=datetime(2026, 12, 3, 10, 0, tzinfo=UTC),
        )


# ---------------------------------------------------------------------------
# 5. Liquidación del turno (Flujo 4, R8)
# ---------------------------------------------------------------------------


async def test_calcular_liquidacion_descuenta_cobertura_os_y_sena_cobrada(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Flujo 4 / R8: `saldo = 50000 - 20000 (OSDE) - 10000 (seña) = 20000`."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    liquidacion = await calcular_liquidacion_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno.id,
        obra_social="OSDE",
    )

    assert _dec(liquidacion.precio_particular) == Decimal("50000.00")
    assert _dec(liquidacion.cobertura_os) == Decimal("20000.00")
    assert _dec(liquidacion.sena_cobrada) == Decimal("10000.00")
    assert _dec(liquidacion.saldo) == Decimal("20000.00")


async def test_calcular_liquidacion_sin_os_nunca_deja_saldo_negativo(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """R8: sin cobertura OS el saldo es `precio - seña`, con piso en cero."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    liquidacion = await calcular_liquidacion_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno.id,
        obra_social=None,
    )

    assert _dec(liquidacion.cobertura_os) == CERO
    assert _dec(liquidacion.saldo) == Decimal("40000.00")


async def test_cobrar_saldo_turno_registra_movimiento_y_aplica_la_sena(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Flujo 4: el cobro del saldo crea el ingreso por 20000 y pasa la seña a `aplicada`."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    movimiento = await cobrar_saldo_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno.id,
        datos=CobrarTurnoInput(medio=MedioPago.TRANSFERENCIA, obra_social="OSDE"),
        actor_id=ctx.odontologo.id,
    )

    assert movimiento.tipo == TipoMovimientoCaja.INGRESO.value
    assert movimiento.medio == MedioPago.TRANSFERENCIA.value
    assert _dec(movimiento.monto) == Decimal("20000.00")
    assert movimiento.turno_id == turno.id
    assert sena.estado == EstadoSena.APLICADA.value


async def test_cobrar_saldo_sin_saldo_pendiente_rechaza_conflicto(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Edge R8: sin saldo pendiente no se crean movimientos de monto cero."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)

    # Sin cobertura OS y sin seña cobrada el saldo es el precio completo: se cobra una vez.
    await cobrar_saldo_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno.id,
        datos=CobrarTurnoInput(medio=MedioPago.EFECTIVO, obra_social="OSDE"),
        actor_id=ctx.odontologo.id,
    )

    with pytest.raises(Conflicto):
        await cobrar_saldo_turno(
            session,
            tenant_id=tenant_a.id,
            turno_id=turno.id,
            datos=CobrarTurnoInput(medio=MedioPago.EFECTIVO, obra_social="OSDE"),
            actor_id=ctx.odontologo.id,
        )


# ---------------------------------------------------------------------------
# 6. Caja diaria: apertura, movimientos, cierre y reapertura (RN-PA-05)
# ---------------------------------------------------------------------------


async def test_abrir_cierre_duplicado_para_la_misma_fecha_rechaza_conflicto(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """D3: un solo cierre por fecha y consultorio."""
    ctx = await _seed_consultorio(session, tenant_a)
    await abrir_cierre_caja(
        session,
        tenant_id=tenant_a.id,
        datos=CierreCajaAbrirInput(fecha=date(2026, 12, 5)),
        actor_id=ctx.odontologo.id,
    )

    with pytest.raises(Conflicto):
        await abrir_cierre_caja(
            session,
            tenant_id=tenant_a.id,
            datos=CierreCajaAbrirInput(fecha=date(2026, 12, 5)),
            actor_id=ctx.odontologo.id,
        )


async def test_cerrar_caja_calcula_total_sistema_y_diferencia_visible(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-05: `total_sistema = ingresos - egresos` y `diferencia = contado - sistema`."""
    ctx = await _seed_consultorio(session, tenant_a)
    cierre = await abrir_cierre_caja(
        session,
        tenant_id=tenant_a.id,
        datos=CierreCajaAbrirInput(fecha=date(2026, 12, 6)),
        actor_id=ctx.odontologo.id,
    )

    ingreso = await registrar_movimiento_caja(
        session,
        tenant_id=tenant_a.id,
        datos=MovimientoCajaCreate(
            tipo=TipoMovimientoCaja.INGRESO,
            concepto="Cobro atención",
            medio=MedioPago.EFECTIVO,
            monto=Decimal("30000.00"),
        ),
        actor_id=ctx.odontologo.id,
    )
    await registrar_movimiento_caja(
        session,
        tenant_id=tenant_a.id,
        datos=MovimientoCajaCreate(
            tipo=TipoMovimientoCaja.EGRESO,
            concepto="Compra de insumos",
            medio=MedioPago.EFECTIVO,
            monto=Decimal("5000.00"),
        ),
        actor_id=ctx.odontologo.id,
    )
    assert ingreso.cierre_id == cierre.id

    cerrado = await cerrar_caja(
        session,
        tenant_id=tenant_a.id,
        cierre_id=cierre.id,
        datos=CierreCajaCerrarInput(total_contado=Decimal("24500.00")),
        actor_id=ctx.odontologo.id,
    )

    assert cerrado.estado == EstadoCierreCaja.CERRADO.value
    assert _dec(cerrado.total_sistema) == Decimal("25000.00")
    assert _dec(cerrado.total_contado) == Decimal("24500.00")
    assert _dec(cerrado.diferencia) == Decimal("-500.00")
    assert cerrado.cerrado_por == ctx.odontologo.id
    assert cerrado.cerrado_at is not None


async def test_cierre_cerrado_es_inmutable_y_no_recibe_movimientos_nuevos(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """R7 / D3: un cierre cerrado no admite movimientos ni un segundo cierre."""
    ctx = await _seed_consultorio(session, tenant_a)
    cierre = await abrir_cierre_caja(
        session,
        tenant_id=tenant_a.id,
        datos=CierreCajaAbrirInput(fecha=date(2026, 12, 7)),
        actor_id=ctx.odontologo.id,
    )
    await registrar_movimiento_caja(
        session,
        tenant_id=tenant_a.id,
        datos=MovimientoCajaCreate(
            tipo=TipoMovimientoCaja.INGRESO,
            concepto="Cobro seña",
            medio=MedioPago.EFECTIVO,
            monto=Decimal("10000.00"),
        ),
        actor_id=ctx.odontologo.id,
    )
    await cerrar_caja(
        session,
        tenant_id=tenant_a.id,
        cierre_id=cierre.id,
        datos=CierreCajaCerrarInput(total_contado=Decimal("10000.00")),
        actor_id=ctx.odontologo.id,
    )

    with pytest.raises(Conflicto):
        await cerrar_caja(
            session,
            tenant_id=tenant_a.id,
            cierre_id=cierre.id,
            datos=CierreCajaCerrarInput(total_contado=Decimal("9000.00")),
            actor_id=ctx.odontologo.id,
        )

    posterior = await registrar_movimiento_caja(
        session,
        tenant_id=tenant_a.id,
        datos=MovimientoCajaCreate(
            tipo=TipoMovimientoCaja.INGRESO,
            concepto="Cobro posterior al cierre",
            medio=MedioPago.DEBITO,
            monto=Decimal("7000.00"),
        ),
        actor_id=ctx.odontologo.id,
    )

    assert posterior.cierre_id is None
    assert _dec(cierre.total_sistema) == Decimal("10000.00")


async def test_reabrir_caja_exige_motivo_y_audita_antes_y_despues(
    session: AsyncSession,
    tenant_a: Tenant,
    auditoria_de,
) -> None:
    """RN-SE-01: la reapertura deja el cierre abierto y un evento con `antes`/`despues`."""
    ctx = await _seed_consultorio(session, tenant_a)
    cierre = await abrir_cierre_caja(
        session,
        tenant_id=tenant_a.id,
        datos=CierreCajaAbrirInput(fecha=date(2026, 12, 8)),
        actor_id=ctx.odontologo.id,
    )
    await cerrar_caja(
        session,
        tenant_id=tenant_a.id,
        cierre_id=cierre.id,
        datos=CierreCajaCerrarInput(total_contado=Decimal("0.00")),
        actor_id=ctx.odontologo.id,
    )

    reabierto = await reabrir_caja(
        session,
        tenant_id=tenant_a.id,
        cierre_id=cierre.id,
        datos=CierreCajaReabrirInput(motivo="Faltó cargar un egreso de insumos"),
        actor_id=ctx.odontologo.id,
    )

    assert reabierto.estado == EstadoCierreCaja.ABIERTO.value
    assert reabierto.reabierto_motivo == "Faltó cargar un egreso de insumos"

    eventos = await auditoria_de("caja.reabrir_cierre")
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.entidad == "cierre_caja"
    assert evento.entidad_id == str(cierre.id)
    assert evento.antes is not None and evento.antes["estado"] == EstadoCierreCaja.CERRADO.value
    assert evento.despues is not None
    assert evento.despues["estado"] == EstadoCierreCaja.ABIERTO.value
    assert evento.despues["motivo"] == "Faltó cargar un egreso de insumos"


async def test_reabrir_un_cierre_abierto_rechaza_la_operacion(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Edge RN-PA-05: solo se reabre lo que está cerrado."""
    ctx = await _seed_consultorio(session, tenant_a)
    cierre = await abrir_cierre_caja(
        session,
        tenant_id=tenant_a.id,
        datos=CierreCajaAbrirInput(fecha=date(2026, 12, 9)),
        actor_id=ctx.odontologo.id,
    )

    with pytest.raises(EntidadInvalida):
        await reabrir_caja(
            session,
            tenant_id=tenant_a.id,
            cierre_id=cierre.id,
            datos=CierreCajaReabrirInput(motivo="Prueba"),
            actor_id=ctx.odontologo.id,
        )


async def test_movimiento_de_caja_con_turno_de_otro_tenant_rechaza_404(
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
) -> None:
    """R4: no se pueden imputar movimientos a turnos de otro consultorio."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)

    with pytest.raises(NoEncontrado):
        await registrar_movimiento_caja(
            session,
            tenant_id=tenant_b.id,
            datos=MovimientoCajaCreate(
                tipo=TipoMovimientoCaja.INGRESO,
                concepto="Movimiento cruzado",
                medio=MedioPago.EFECTIVO,
                monto=Decimal("1000.00"),
                turno_id=turno.id,
            ),
            actor_id=ctx.odontologo.id,
        )


async def test_vencer_sena_de_otro_tenant_no_la_encuentra(
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
) -> None:
    """R4: el aislamiento multi-tenant también cubre señas."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)

    with pytest.raises(NoEncontrado):
        await vencer_sena_impaga(
            session,
            tenant_id=tenant_b.id,
            sena_id=sena.id,
            ahora=datetime.now(UTC) + timedelta(days=2),
        )


# ---------------------------------------------------------------------------
# 7. Triangulación: bordes de la política de cancelación y del aislamiento
# ---------------------------------------------------------------------------


async def test_resolver_cancelacion_en_el_limite_exacto_de_horas_devuelve_la_sena(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Borde RN-PA-04: con exactamente `cancelacion_hs` (24 h) la seña se devuelve."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)
    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=ctx.odontologo.id,
    )

    devuelta = await resolver_sena_por_cancelacion(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaResolverCancelacionInput(motivo="Justo en término"),
        actor_id=ctx.odontologo.id,
        ahora=datetime(2026, 11, 30, 10, 0, tzinfo=UTC),
    )

    assert devuelta.estado == EstadoSena.DEVUELTA.value


async def test_resolver_cancelacion_de_sena_impaga_la_devuelve_sin_tocar_el_turno(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-04: sin dinero cobrado no hay retención posible: la seña se libera."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)

    devuelta = await resolver_sena_por_cancelacion(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaResolverCancelacionInput(motivo="Canceló antes de pagar"),
        actor_id=ctx.odontologo.id,
        ahora=datetime(2026, 12, 1, 9, 0, tzinfo=UTC),
    )

    assert devuelta.estado == EstadoSena.DEVUELTA.value
    assert turno.sena_cobrada is False


async def test_cobrar_sena_de_otro_tenant_no_la_encuentra(
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
) -> None:
    """R4: cobrar una seña de otro consultorio responde 404, nunca 200."""
    ctx = await _seed_consultorio(session, tenant_a)
    turno = await _crear_turno_con_sena(session, tenant_a, ctx)
    sena = await _sena_de(session, turno)

    with pytest.raises(NoEncontrado):
        await cobrar_sena(
            session,
            tenant_id=tenant_b.id,
            sena_id=sena.id,
            datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
            actor_id=ctx.odontologo.id,
        )

    assert sena.estado == EstadoSena.PENDIENTE.value


async def test_cerrar_caja_sin_movimientos_deja_total_cero_y_diferencia_igual_al_contado(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Borde RN-PA-05: un cierre vacío con contado 0 no inventa diferencia."""
    ctx = await _seed_consultorio(session, tenant_a)
    cierre = await abrir_cierre_caja(
        session,
        tenant_id=tenant_a.id,
        datos=CierreCajaAbrirInput(fecha=date(2026, 12, 10)),
        actor_id=ctx.odontologo.id,
    )

    cerrado = await cerrar_caja(
        session,
        tenant_id=tenant_a.id,
        cierre_id=cierre.id,
        datos=CierreCajaCerrarInput(total_contado=Decimal("1500.00")),
        actor_id=ctx.odontologo.id,
    )

    assert _dec(cerrado.total_sistema) == CERO
    assert _dec(cerrado.diferencia) == Decimal("1500.00")
