"""Presentación, resultado y anulación de liquidaciones (C-13, tareas 3.3 y 3.4).

Cubre, con el glosario de `05_reglas_de_negocio.md` y `07_flujos_principales.md`:
1. Presentación `borrador → presentada`: exige al menos un turno con monto y fija actor/fecha.
2. Resultado de la OS: `presentada → pagada` (reconoce todo) o `→ con_debitos` (recortes),
   con coherencia entre el resultado y los montos reconocidos (D4, US-041).
3. Anulación: baja lógica `borrador → anulada` que conserva cabecera y detalle y libera el turno
   (R7, D3), rechazada en cualquier otro estado, con flip de `vigente` al pagar.
4. Auditoría append-only de la presentación, el resultado y la anulación (RN-SE-01, R9).
"""

import asyncio
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas_liquidaciones import (
    LiquidacionOSAnularInput,
    LiquidacionOSCerrarInput,
    LiquidacionOSCreate,
    LiquidacionOSDebitosInput,
    LiquidacionOSDetalleDebitoInput,
    LiquidacionOSRead,
    ResultadoOSInput,
)
from app.application.liquidaciones import (
    ADVERTENCIA_COMPLEMENTARIA,
    anular_liquidacion,
    generar_borrador,
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
from app.shared.exceptions import Conflicto, EntidadInvalida

CERO = Decimal("0.00")
INICIO = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


class _Consultorio:
    """Contexto mínimo con una prestación cuyo arancel OSDE es 20000 sobre 50000."""

    def __init__(self) -> None:
        self.usuario: Usuario
        self.paciente: Paciente
        self.sillon: Sillon
        self.prestacion: Prestacion


async def _seed(session: AsyncSession, tenant: Tenant) -> _Consultorio:
    ctx = _Consultorio()
    ctx.usuario = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-estados-{tenant.slug}@consultorio.test",
        nombre="Dr. Estados",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-60140",
        activo=True,
    )
    ctx.paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Bruno Estados",
        dni=f"3{tenant.slug[-1].upper()}554441",
        telefono="+5491188889999",
        optin_wa=True,
        activo=True,
    )
    ctx.sillon = Sillon(
        id=uuid.uuid4(), tenant_id=tenant.id, nombre=f"Box Estados {tenant.slug}", activo=True
    )
    ctx.prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Consulta Estados {tenant.slug}",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([ctx.usuario, ctx.paciente, ctx.sillon, ctx.prestacion])
    await session.flush()
    session.add(
        CoberturaOS(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            obra_social="OSDE",
            prestacion_id=ctx.prestacion.id,
            arancel=Decimal("20000.00"),
            copago=Decimal("0.00"),
            vigencia_desde=date(2020, 1, 1),
            vigencia_hasta=None,
            activa=True,
        )
    )
    await session.flush()
    return ctx


async def _turno(session: AsyncSession, tenant: Tenant, ctx: _Consultorio, *, hora: int) -> Turno:
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
    session: AsyncSession, tenant: Tenant, ctx: _Consultorio, *, turnos: int = 1
) -> LiquidacionOSRead:
    horas = [9, 11, 15, 17]
    for hora in horas[:turnos]:
        await _turno(session, tenant, ctx, hora=hora)
    return await generar_borrador(
        session,
        tenant_id=tenant.id,
        datos=LiquidacionOSCreate(obra_social="OSDE", periodo="202611"),
        actor_id=ctx.usuario.id,
    )


async def _presentada(
    session: AsyncSession, tenant: Tenant, ctx: _Consultorio, *, turnos: int = 1
) -> LiquidacionOSRead:
    borrador = await _borrador(session, tenant, ctx, turnos=turnos)
    return await presentar_liquidacion(
        session,
        tenant_id=tenant.id,
        liquidacion_id=borrador.id,
        actor_id=ctx.usuario.id,
    )


def _resultado(
    *detalles: LiquidacionOSDetalleDebitoInput, resultado: str = "con_debitos"
) -> ResultadoOSInput:
    return ResultadoOSInput(resultado=resultado, detalles=list(detalles))


def _recorte(
    turno_id: uuid.UUID, monto: str, motivo: str | None = None
) -> LiquidacionOSDetalleDebitoInput:
    return LiquidacionOSDetalleDebitoInput(
        turno_id=turno_id, monto_reconocido=Decimal(monto), debito_motivo=motivo
    )


async def _eventos(session: AsyncSession, accion: str) -> list[Auditoria]:
    return list(
        (await session.execute(select(Auditoria).where(Auditoria.accion == accion))).scalars().all()
    )


async def _estado_orm(
    session: AsyncSession, tenant: Tenant, liquidacion_id: uuid.UUID
) -> LiquidacionOS:
    return (
        await session.execute(
            select(LiquidacionOS).where(
                LiquidacionOS.id == liquidacion_id,
                LiquidacionOS.tenant_id == tenant.id,
            )
        )
    ).scalar_one()


async def _detalles_orm(
    session: AsyncSession, tenant: Tenant, liquidacion_id: uuid.UUID
) -> list[LiquidacionOSDetalle]:
    return list(
        (
            await session.execute(
                select(LiquidacionOSDetalle).where(
                    LiquidacionOSDetalle.tenant_id == tenant.id,
                    LiquidacionOSDetalle.liquidacion_id == liquidacion_id,
                )
            )
        )
        .scalars()
        .all()
    )


async def _cantidad_liquidaciones(session: AsyncSession, tenant: Tenant) -> int:
    """Cuántas liquidaciones tiene el consultorio (para verificar que no se crearen de más)."""
    return len(
        (await session.execute(select(LiquidacionOS).where(LiquidacionOS.tenant_id == tenant.id)))
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# 3.3 Presentación del borrador
# ---------------------------------------------------------------------------


async def test_presentar_cierra_el_borrador_con_actor_y_fecha(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D4: el cierre pasa a `presentada`, fija actor/fecha y registra la auditoría."""
    ctx = await _seed(session, tenant_a)
    borrador = await _borrador(session, tenant_a, ctx, turnos=2)

    presentada = await presentar_liquidacion(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=borrador.id,
        actor_id=ctx.usuario.id,
        datos=LiquidacionOSCerrarInput(observaciones="Presentada el 30/11"),
    )

    assert presentada.estado is EstadoLiquidacionOS.PRESENTADA
    assert presentada.presentada_por == ctx.usuario.id
    assert presentada.presentada_at is not None
    assert presentada.presentada_at.tzinfo is not None
    assert presentada.observaciones == "Presentada el 30/11"
    assert presentada.total == Decimal("40000.00")

    eventos = await _eventos(session, "liquidacion.presentar")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == str(borrador.id)
    assert eventos[0].actor_id == ctx.usuario.id
    assert eventos[0].antes == {"estado": "borrador"}
    assert eventos[0].despues == {"estado": "presentada"}


async def test_presentar_un_borrador_vacio_da_422(session: AsyncSession, tenant_a: Tenant) -> None:
    """Defensivo: un borrador sin turnos no se puede presentar y sigue en `borrador`."""
    ctx = await _seed(session, tenant_a)
    vacio = LiquidacionOS(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        obra_social="OSDE",
        periodo="202611",
        estado=EstadoLiquidacionOS.BORRADOR.value,
        total=CERO,
        created_by=ctx.usuario.id,
    )
    session.add(vacio)
    await session.flush()

    with pytest.raises(EntidadInvalida):
        await presentar_liquidacion(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=vacio.id,
            actor_id=ctx.usuario.id,
        )

    assert (await _estado_orm(session, tenant_a, vacio.id)).estado == (
        EstadoLiquidacionOS.BORRADOR.value
    )


async def test_presentar_dos_veces_da_409(session: AsyncSession, tenant_a: Tenant) -> None:
    """D4: `presentada` no vuelve a presentarse; el grafo sólo permite pagada/con_debitos."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx)

    with pytest.raises(Conflicto):
        await presentar_liquidacion(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            actor_id=ctx.usuario.id,
        )


# ---------------------------------------------------------------------------
# 3.3 Resultado informado por la obra social
# ---------------------------------------------------------------------------


async def test_resultado_con_recortes_deja_la_liquidacion_con_debitos(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """US-041: un recorte con motivo transiciona a `con_debitos` y guarda el reconocido."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx)
    turno_id = presentada.detalles[0].turno_id

    resultante = await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=presentada.id,
        datos=_resultado(_recorte(turno_id, "15000.00", "Arancel fuera de nomenclador")),
        actor_id=ctx.usuario.id,
    )

    assert resultante.estado is EstadoLiquidacionOS.CON_DEBITOS
    assert resultante.total == Decimal("20000.00")
    assert resultante.total_reconocido == Decimal("15000.00")
    assert resultante.resuelta_por == ctx.usuario.id
    assert resultante.resuelta_at is not None
    assert resultante.detalles[0].monto_reconocido == Decimal("15000.00")
    assert resultante.detalles[0].debito_motivo == "Arancel fuera de nomenclador"
    assert resultante.detalles[0].vigente is True

    eventos = await _eventos(session, "liquidacion.resultado")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == str(presentada.id)
    assert eventos[0].despues["estado"] == "con_debitos"  # type: ignore[index]
    assert eventos[0].despues["total_reconocido"] == "15000.00"  # type: ignore[index]


async def test_resultado_que_reconoce_el_total_deja_pagada_y_baja_la_vigencia(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D3/D4: reconocer el total cierra como `pagada` y libera todos los turnos."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx, turnos=2)

    resultante = await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=presentada.id,
        datos=_resultado(
            *[_recorte(detalle.turno_id, "20000.00") for detalle in presentada.detalles],
            resultado="pagada",
        ),
        actor_id=ctx.usuario.id,
    )

    assert resultante.estado is EstadoLiquidacionOS.PAGADA
    assert resultante.total_reconocido == Decimal("40000.00")
    assert [detalle.vigente for detalle in resultante.detalles] == [False, False]
    detalles = await _detalles_orm(session, tenant_a, presentada.id)
    assert all(detalle.vigente is False for detalle in detalles)


async def test_resultado_pagada_con_reconocido_menor_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R8: `pagada` exige reconocer el total; un recorte debe informarse como `con_debitos`."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx)
    turno_id = presentada.detalles[0].turno_id

    with pytest.raises(EntidadInvalida):
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=_resultado(_recorte(turno_id, "15000.00", "Débito"), resultado="pagada"),
            actor_id=ctx.usuario.id,
        )

    cabecera = await _estado_orm(session, tenant_a, presentada.id)
    assert cabecera.estado == EstadoLiquidacionOS.PRESENTADA.value
    assert cabecera.total_reconocido is None
    detalles = await _detalles_orm(session, tenant_a, presentada.id)
    assert detalles[0].monto_reconocido is None
    assert detalles[0].debito_motivo is None


async def test_resultado_con_debitos_sin_recortes_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """Coherencia inversa: `con_debitos` exige que la OS reconozca menos que el total."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx)

    with pytest.raises(EntidadInvalida):
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=_resultado(
                _recorte(presentada.detalles[0].turno_id, "20000.00", "Motivo sin recorte")
            ),
            actor_id=ctx.usuario.id,
        )

    assert (await _estado_orm(session, tenant_a, presentada.id)).estado == (
        EstadoLiquidacionOS.PRESENTADA.value
    )


async def test_resultado_que_no_informa_todos_los_turnos_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R8: el resultado tiene que informar todos los turnos para que el total sea coherente."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx, turnos=2)

    with pytest.raises(EntidadInvalida):
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=_resultado(
                _recorte(presentada.detalles[0].turno_id, "15000.00", "Sólo un turno")
            ),
            actor_id=ctx.usuario.id,
        )


async def test_recorte_sin_motivo_dentro_del_resultado_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """US-041: cada recorte necesita su motivo, aunque el resultado traiga otro motivo válido."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx, turnos=2)
    primero, segundo = presentada.detalles

    with pytest.raises(EntidadInvalida):
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=_resultado(
                _recorte(primero.turno_id, "15000.00", "Motivo del primero"),
                _recorte(segundo.turno_id, "10000.00"),
            ),
            actor_id=ctx.usuario.id,
        )

    detalles = await _detalles_orm(session, tenant_a, presentada.id)
    assert all(detalle.monto_reconocido is None for detalle in detalles)


async def test_borrador_a_pagada_da_409(session: AsyncSession, tenant_a: Tenant) -> None:
    """D4: no se saltea la presentación; `borrador → pagada` está fuera del grafo."""
    ctx = await _seed(session, tenant_a)
    borrador = await _borrador(session, tenant_a, ctx)

    with pytest.raises(Conflicto):
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=borrador.id,
            datos=_resultado(
                _recorte(borrador.detalles[0].turno_id, "15000.00", "Débito"),
                resultado="con_debitos",
            ),
            actor_id=ctx.usuario.id,
        )

    assert (await _estado_orm(session, tenant_a, borrador.id)).estado == (
        EstadoLiquidacionOS.BORRADOR.value
    )


# ---------------------------------------------------------------------------
# Bloque E: resultado todo-o-nada, total desde el detalle y `con_debits → pagada`
# ---------------------------------------------------------------------------


async def test_el_resultado_con_turno_repetido_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D10/BLOCKER 2: un `turno_id` repetido se rechaza y no aplica ningún monto."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx, turnos=2)
    turno_id = presentada.detalles[0].turno_id
    # `model_construct` saltea la validación del schema para llegar a la defensa en
    # profundidad del caso de uso (el schema ya rechaza el payload en el borde).
    datos = ResultadoOSInput.model_construct(
        resultado="pagada",
        observaciones=None,
        detalles=[
            LiquidacionOSDetalleDebitoInput(
                turno_id=turno_id, monto_reconocido=Decimal("20000.00")
            ),
            LiquidacionOSDetalleDebitoInput(
                turno_id=turno_id, monto_reconocido=Decimal("20000.00")
            ),
        ],
    )

    with pytest.raises(EntidadInvalida):
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=datos,
            actor_id=ctx.usuario.id,
        )

    cabecera = await _estado_orm(session, tenant_a, presentada.id)
    assert cabecera.estado == EstadoLiquidacionOS.PRESENTADA.value
    assert cabecera.total_reconocido is None
    detalles = await _detalles_orm(session, tenant_a, presentada.id)
    assert all(detalle.monto_reconocido is None for detalle in detalles)


async def test_el_total_reconocido_se_recalcula_desde_el_detalle_persistido(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D10/R8: el total reconocido es la suma del detalle persistido, no del payload."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx, turnos=2)
    primero, segundo = presentada.detalles

    resultante = await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=presentada.id,
        datos=_resultado(
            _recorte(primero.turno_id, "20000.00"),
            _recorte(segundo.turno_id, "0.00", "Fuera de nomenclador"),
            resultado="con_debitos",
        ),
        actor_id=ctx.usuario.id,
    )

    detalles = await _detalles_orm(session, tenant_a, presentada.id)
    suma_persistida = sum(
        (detalle.monto_reconocido for detalle in detalles if detalle.monto_reconocido is not None),
        CERO,
    )
    assert resultante.total_reconocido == suma_persistida == Decimal("20000.00")
    assert resultante.total == Decimal("40000.00")
    assert resultante.saldo_debito == Decimal("20000.00")
    assert (await _estado_orm(session, tenant_a, presentada.id)).total_reconocido == Decimal(
        "20000.00"
    )


async def test_la_con_debitos_pasa_a_pagada_conservando_el_saldo_reconocido(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D4 (enmienda): `con_debitos → pagada` conserva el débito y el saldo reconocido."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx)
    turno_id = presentada.detalles[0].turno_id
    con_debitos = await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=presentada.id,
        datos=_resultado(_recorte(turno_id, "15000.00", "Arancel fuera de nomenclador")),
        actor_id=ctx.usuario.id,
    )
    assert con_debitos.estado is EstadoLiquidacionOS.CON_DEBITOS
    assert con_debitos.total_reconocido == Decimal("15000.00")

    # La OS paga el saldo reconocido: no vuelve a informar el motivo, se conserva el cargado.
    pagada = await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=presentada.id,
        datos=_resultado(_recorte(turno_id, "15000.00"), resultado="pagada"),
        actor_id=ctx.usuario.id,
    )

    assert pagada.estado is EstadoLiquidacionOS.PAGADA
    assert pagada.total_reconocido == Decimal("15000.00")
    assert pagada.total == Decimal("20000.00")
    assert pagada.saldo_debito == Decimal("5000.00")
    assert pagada.detalles[0].debito_motivo == "Arancel fuera de nomenclador"
    assert pagada.detalles[0].monto_reconocido == Decimal("15000.00")


async def test_la_con_debitos_pasa_a_pagada_con_un_reconocido_menor_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D4 (enmienda): la OS no puede reconocer menos de lo que ya había reconocido."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx)
    turno_id = presentada.detalles[0].turno_id
    await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=presentada.id,
        datos=_resultado(_recorte(turno_id, "15000.00", "Arancel fuera de nomenclador")),
        actor_id=ctx.usuario.id,
    )

    with pytest.raises(EntidadInvalida):
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=_resultado(_recorte(turno_id, "10000.00", "Otro débito"), resultado="pagada"),
            actor_id=ctx.usuario.id,
        )

    cabecera = await _estado_orm(session, tenant_a, presentada.id)
    assert cabecera.estado == EstadoLiquidacionOS.CON_DEBITOS.value
    assert cabecera.total_reconocido == Decimal("15000.00")


async def test_el_resultado_incompleto_da_422_informando_cuantos_turnos_faltan(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """E.6: el 422 dice cuántos turnos faltan y cuáles (sin datos del paciente)."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx, turnos=3)
    informe, *pendientes = presentada.detalles

    with pytest.raises(EntidadInvalida) as error:
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=_resultado(_recorte(informe.turno_id, "20000.00"), resultado="pagada"),
            actor_id=ctx.usuario.id,
        )

    mensaje = str(error.value)
    assert "faltan 2" in mensaje
    assert str(pendientes[0].turno_id) in mensaje
    assert str(pendientes[1].turno_id) in mensaje
    assert ctx.paciente.dni not in mensaje
    assert ctx.paciente.telefono not in mensaje


async def test_el_resultado_con_turnos_de_mas_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """E.6: un turno ajeno a la liquidación no se puede informar en el resultado."""
    ctx = await _seed(session, tenant_a)
    presentada = await _presentada(session, tenant_a, ctx)
    ajeno = await _turno(session, tenant_a, ctx, hora=13)

    with pytest.raises(EntidadInvalida) as error:
        await registrar_resultado(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=presentada.id,
            datos=_resultado(
                _recorte(presentada.detalles[0].turno_id, "20000.00"),
                _recorte(ajeno.id, "20000.00"),
                resultado="pagada",
            ),
            actor_id=ctx.usuario.id,
        )

    assert str(ajeno.id) in str(error.value)
    cabecera = await _estado_orm(session, tenant_a, presentada.id)
    assert cabecera.estado == EstadoLiquidacionOS.PRESENTADA.value


# ---------------------------------------------------------------------------
# Bloque E: serialización de las mutaciones (D11)
# ---------------------------------------------------------------------------


async def test_la_edicion_concurrente_de_una_presentada_da_409_y_no_muta_el_detalle(
    session: AsyncSession, tenant_a: Tenant, db_url: str, dialecto: str
) -> None:
    """D11: con la cabecera bloqueada, la edición perdedora recibe 409 y no pisa el detalle."""
    if dialecto != "postgresql":
        pytest.skip("el lock pesimista de cabecera sólo lo aplica Postgres")

    ctx = await _seed(session, tenant_a)
    borrador = await _borrador(session, tenant_a, ctx)
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
    await session.commit()

    engine = create_engine_for(db_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as otra:
        # La transacción principal presenta la liquidación y mantiene el lock de cabecera.
        await presentar_liquidacion(
            session, tenant_id=tenant_a.id, liquidacion_id=borrador.id, actor_id=ctx.usuario.id
        )
        # La otra transacción intenta editar los débitos: queda esperando el lock.
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
        await asyncio.sleep(0.2)
        assert not tarea.done(), "la edición concurrente tiene que quedar esperando el lock"
        await session.commit()

        with pytest.raises(Conflicto):
            await asyncio.wait_for(tarea, timeout=15)

    detalles = await _detalles_orm(session, tenant_a, borrador.id)
    assert detalles[0].monto_reconocido == Decimal("15000.00")
    assert detalles[0].debito_motivo == "Primer pase"
    assert (await _estado_orm(session, tenant_a, borrador.id)).estado == (
        EstadoLiquidacionOS.PRESENTADA.value
    )


# ---------------------------------------------------------------------------
# 3.4 Anulación y liberación de turnos (R7, D3)
# ---------------------------------------------------------------------------


async def test_anular_el_borrador_conserva_el_detalle_y_libera_el_turno(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R7/D3: anular es baja lógica; el detalle sigue existiendo y el turno se re-liquida."""
    ctx = await _seed(session, tenant_a)
    borrador = await _borrador(session, tenant_a, ctx, turnos=2)
    turnos_originales = {detalle.turno_id for detalle in borrador.detalles}

    anulada = await anular_liquidacion(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=borrador.id,
        datos=LiquidacionOSAnularInput(motivo="Se cargó el período equivocado"),
        actor_id=ctx.usuario.id,
    )

    assert anulada.estado is EstadoLiquidacionOS.ANULADA
    assert anulada.anulada_motivo == "Se cargó el período equivocado"
    assert len(anulada.detalles) == 2
    assert all(detalle.vigente is False for detalle in anulada.detalles)
    assert len(await _detalles_orm(session, tenant_a, borrador.id)) == 2

    nueva = await generar_borrador(
        session,
        tenant_id=tenant_a.id,
        datos=LiquidacionOSCreate(obra_social="OSDE", periodo="202611"),
        actor_id=ctx.usuario.id,
    )

    assert nueva.id != borrador.id
    assert {detalle.turno_id for detalle in nueva.detalles} == turnos_originales
    assert all(detalle.vigente is True for detalle in nueva.detalles)


async def test_anular_no_ejecuta_ningun_delete_fisico(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R7: cabecera y detalle siguen en la DB; la auditoría guarda antes/después."""
    ctx = await _seed(session, tenant_a)
    borrador = await _borrador(session, tenant_a, ctx, turnos=2)

    await anular_liquidacion(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=borrador.id,
        datos=LiquidacionOSAnularInput(motivo="Baja lógica por error de carga"),
        actor_id=ctx.usuario.id,
    )

    assert len(await _detalles_orm(session, tenant_a, borrador.id)) == 2
    cabeceras = (
        (await session.execute(select(LiquidacionOS).where(LiquidacionOS.id == borrador.id)))
        .scalars()
        .all()
    )
    assert len(cabeceras) == 1
    assert cabeceras[0].estado == EstadoLiquidacionOS.ANULADA.value

    eventos = await _eventos(session, "liquidacion.anular")
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.antes["estado"] == "borrador"  # type: ignore[index]
    assert evento.despues["estado"] == "anulada"  # type: ignore[index]
    assert evento.despues["motivo"] == "Baja lógica por error de carga"  # type: ignore[index]
    payload = json.dumps([evento.antes, evento.despues], default=str)
    assert ctx.paciente.dni not in payload
    assert ctx.paciente.telefono not in payload


async def _llevar_a(
    session: AsyncSession, tenant: Tenant, ctx: _Consultorio, estado: EstadoLiquidacionOS
) -> LiquidacionOSRead:
    """Lleva una liquidación a `presentada`, `con_debitos` o `pagada` por el camino real."""
    presentada = await _presentada(session, tenant, ctx)
    if estado is EstadoLiquidacionOS.PRESENTADA:
        return presentada
    turno_id = presentada.detalles[0].turno_id
    if estado is EstadoLiquidacionOS.CON_DEBITOS:
        return await registrar_resultado(
            session,
            tenant_id=tenant.id,
            liquidacion_id=presentada.id,
            datos=_resultado(_recorte(turno_id, "15000.00", "Débito de la OS")),
            actor_id=ctx.usuario.id,
        )
    return await registrar_resultado(
        session,
        tenant_id=tenant.id,
        liquidacion_id=presentada.id,
        datos=_resultado(_recorte(turno_id, "20000.00"), resultado="pagada"),
        actor_id=ctx.usuario.id,
    )


@pytest.mark.parametrize(
    "estado",
    [
        EstadoLiquidacionOS.PRESENTADA,
        EstadoLiquidacionOS.CON_DEBITOS,
        EstadoLiquidacionOS.PAGADA,
    ],
)
async def test_anular_fuera_de_borrador_da_409(
    session: AsyncSession, tenant_a: Tenant, estado: EstadoLiquidacionOS
) -> None:
    """R7: sólo se anula un borrador; los demás estados conservan su estado y su detalle."""
    ctx = await _seed(session, tenant_a)
    liquidacion = await _llevar_a(session, tenant_a, ctx, estado)

    with pytest.raises(Conflicto):
        await anular_liquidacion(
            session,
            tenant_id=tenant_a.id,
            liquidacion_id=liquidacion.id,
            datos=LiquidacionOSAnularInput(motivo="Intento de baja"),
            actor_id=ctx.usuario.id,
        )

    cabecera = await _estado_orm(session, tenant_a, liquidacion.id)
    assert cabecera.estado == estado.value
    assert cabecera.anulada_motivo is None
    detalles = await _detalles_orm(session, tenant_a, liquidacion.id)
    assert len(detalles) == 1


async def test_tras_pagar_el_alta_complementaria_no_reclama_los_turnos_pagados(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D9/D6: la complementaria excluye el turno ya cobrado y avisa por `advertencias`."""
    ctx = await _seed(session, tenant_a)
    pagada = await _borrador(session, tenant_a, ctx)
    await presentar_liquidacion(
        session, tenant_id=tenant_a.id, liquidacion_id=pagada.id, actor_id=ctx.usuario.id
    )
    await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=pagada.id,
        datos=_resultado(_recorte(pagada.detalles[0].turno_id, "20000.00"), resultado="pagada"),
        actor_id=ctx.usuario.id,
    )
    ya_cobrado = pagada.detalles[0].turno_id

    # Un turno finalizado más tarde es el único que se puede reclamar en la complementaria.
    nuevo = await _turno(session, tenant_a, ctx, hora=11)

    complementaria = await generar_borrador(
        session,
        tenant_id=tenant_a.id,
        datos=LiquidacionOSCreate(obra_social="OSDE", periodo="202611"),
        actor_id=ctx.usuario.id,
    )

    assert complementaria.estado is EstadoLiquidacionOS.BORRADOR
    assert [detalle.turno_id for detalle in complementaria.detalles] == [nuevo.id]
    assert ya_cobrado not in {detalle.turno_id for detalle in complementaria.detalles}
    assert complementaria.total == Decimal("20000.00")
    assert complementaria.advertencias[0] == ADVERTENCIA_COMPLEMENTARIA
    assert any(str(ya_cobrado) in aviso for aviso in complementaria.advertencias)


async def test_la_complementaria_sin_turnos_nuevos_da_422(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D9: si todos los turnos del período ya fueron liquidados, no hay nada que reclamar."""
    ctx = await _seed(session, tenant_a)
    pagada = await _borrador(session, tenant_a, ctx)
    await presentar_liquidacion(
        session, tenant_id=tenant_a.id, liquidacion_id=pagada.id, actor_id=ctx.usuario.id
    )
    await registrar_resultado(
        session,
        tenant_id=tenant_a.id,
        liquidacion_id=pagada.id,
        datos=_resultado(_recorte(pagada.detalles[0].turno_id, "20000.00"), resultado="pagada"),
        actor_id=ctx.usuario.id,
    )

    with pytest.raises(EntidadInvalida) as error:
        await generar_borrador(
            session,
            tenant_id=tenant_a.id,
            datos=LiquidacionOSCreate(obra_social="OSDE", periodo="202611"),
            actor_id=ctx.usuario.id,
        )

    assert "no hay turnos nuevos para liquidar en ese período" in str(error.value)
    assert await _cantidad_liquidaciones(session, tenant_a) == 1
