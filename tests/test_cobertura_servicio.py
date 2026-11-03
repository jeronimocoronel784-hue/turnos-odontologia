"""Servicio compartido de resolución de cobertura (C-13, tarea 1.2, D1, R11).

Cubre con DB real (Postgres en CI, SQLite local):
1. Lookup de una prestación por obra social case-insensitive (igual que C-10).
2. Aislamiento multi-tenant del padrón `CoberturaOS` (R4).
3. Lote de varias prestaciones en una sola consulta, mismo resultado que el lookup individual.
4. Adaptador `calcular_montos_item_presupuesto`: firma/tupla intactas y arancel vencido (D2).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.cobertura import (
    calcular_montos_item_presupuesto,
    resolver_cobertura_prestacion,
    resolver_coberturas_lote,
)
from app.domain.cobertura_os import CoberturaOS, EstadoArancel
from app.domain.prestacion import Prestacion
from app.domain.tenant import Tenant
from app.shared.exceptions import NoEncontrado

FECHA = date(2026, 11, 15)


async def _prestacion(
    session: AsyncSession,
    tenant: Tenant,
    *,
    nombre: str,
    precio: str = "50000.00",
) -> Prestacion:
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=nombre,
        duracion_min=30,
        precio_particular=Decimal(precio),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add(prestacion)
    await session.flush()
    return prestacion


async def _convenio(
    session: AsyncSession,
    tenant: Tenant,
    prestacion: Prestacion,
    *,
    obra_social: str = "OSDE",
    arancel: str = "30000.00",
    vigencia_desde: date = date(2026, 1, 1),
    vigencia_hasta: date | None = None,
    activa: bool = True,
) -> CoberturaOS:
    cobertura = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        obra_social=obra_social,
        prestacion_id=prestacion.id,
        arancel=Decimal(arancel),
        copago=Decimal("0.00"),
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        activa=activa,
    )
    session.add(cobertura)
    await session.flush()
    return cobertura


async def test_lookup_resuelve_el_convenio_sin_importar_mayusculas(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """RN-OS-01: `osde` en el pedido encuentra el convenio cargado como `OSDE`."""
    prestacion = await _prestacion(session, tenant_a, nombre="Consulta de control")
    await _convenio(session, tenant_a, prestacion, obra_social="OSDE")

    resolucion = await resolver_cobertura_prestacion(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prestacion.id,
        cantidad=1,
        obra_social="osde",
        fecha_referencia=FECHA,
    )

    assert resolucion.estado_arancel is EstadoArancel.VIGENTE
    assert resolucion.cobertura == Decimal("30000.00")
    assert resolucion.monto_a_cargo == Decimal("20000.00")


async def test_lookup_no_cruza_el_padron_de_otro_tenant(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """R4: el convenio de otro consultorio no aplica y una prestación ajena responde 404."""
    prestacion = await _prestacion(session, tenant_a, nombre="Obturación")
    await _convenio(session, tenant_a, prestacion)
    prestacion_ajena = await _prestacion(session, tenant_b, nombre="Obturación ajena")
    await _convenio(session, tenant_b, prestacion_ajena)

    sin_convenio = await resolver_cobertura_prestacion(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prestacion.id,
        cantidad=1,
        obra_social="SWISS MEDICAL",
        fecha_referencia=FECHA,
    )
    assert sin_convenio.estado_arancel is EstadoArancel.SIN_COBERTURA
    assert sin_convenio.monto_a_cargo == Decimal("50000.00")

    with pytest.raises(NoEncontrado):
        await resolver_cobertura_prestacion(
            session,
            tenant_id=tenant_a.id,
            prestacion_id=prestacion_ajena.id,
            cantidad=1,
            obra_social="OSDE",
            fecha_referencia=FECHA,
        )


async def test_lote_devuelve_lo_mismo_que_el_lookup_individual_en_una_sola_consulta(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D1: el lote resuelve varias prestaciones sin N+1 y con el mismo resultado."""
    con_convenio = await _prestacion(session, tenant_a, nombre="Limpieza", precio="40000.00")
    sin_convenio = await _prestacion(session, tenant_a, nombre="Radiografía", precio="12000.00")
    await _convenio(session, tenant_a, con_convenio, arancel="25000.00")

    consultas: list[str] = []
    engine = session.sync_session.bind
    assert engine is not None  # guarda explícita del binding de test

    def _contar(_conn: object, _cursor: object, sentencia: str, *_params: object) -> None:
        consultas.append(sentencia)

    event.listen(engine, "before_cursor_execute", _contar)
    try:
        lote = await resolver_coberturas_lote(
            session,
            tenant_id=tenant_a.id,
            prestacion_ids=[con_convenio.id, sin_convenio.id],
            obra_social="OSDE",
            fecha_referencia=FECHA,
        )
    finally:
        event.remove(engine, "before_cursor_execute", _contar)

    assert set(lote) == {con_convenio.id, sin_convenio.id}
    assert lote[con_convenio.id].cobertura == Decimal("25000.00")
    assert lote[con_convenio.id].monto_a_cargo == Decimal("15000.00")
    assert lote[sin_convenio.id].estado_arancel is EstadoArancel.SIN_COBERTURA
    assert lote[sin_convenio.id].monto_a_cargo == Decimal("12000.00")

    # Una query de prestaciones + una de convenios: nada de N+1 por prestación.
    assert len(consultas) == 2, consultas

    for prestacion in (con_convenio, sin_convenio):
        individual = await resolver_cobertura_prestacion(
            session,
            tenant_id=tenant_a.id,
            prestacion_id=prestacion.id,
            cantidad=1,
            obra_social="OSDE",
            fecha_referencia=FECHA,
        )
        assert lote[prestacion.id] == individual


async def test_adaptador_de_presupuestos_conserva_la_tupla_con_arancel_vencido(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D2: C-10 hereda la regla del arancel vencido sin cambiar su contrato de 3 montos."""
    prestacion = await _prestacion(session, tenant_a, nombre="Endodoncia")
    await _convenio(
        session,
        tenant_a,
        prestacion,
        arancel="30000.00",
        vigencia_desde=date(2025, 1, 1),
        vigencia_hasta=date(2026, 10, 31),
    )

    precio_unit, cobertura_total, a_cargo_total = await calcular_montos_item_presupuesto(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prestacion.id,
        cantidad=2,
        obra_social="OSDE",
        fecha_referencia=FECHA,
    )

    assert precio_unit == Decimal("50000.00")
    assert cobertura_total == Decimal("60000.00")
    assert a_cargo_total == Decimal("40000.00")


async def test_adaptador_de_presupuestos_sin_obra_social_es_particular(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """R8: sin obra social el adaptador devuelve cobertura cero y el subtotal a cargo."""
    prestacion = await _prestacion(session, tenant_a, nombre="Consulta particular")
    await _convenio(session, tenant_a, prestacion)

    assert await calcular_montos_item_presupuesto(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prestacion.id,
        cantidad=3,
        obra_social=None,
        fecha_referencia=FECHA,
    ) == (
        Decimal("50000.00"),
        Decimal("0.00"),
        Decimal("150000.00"),
    )


async def test_adaptador_de_presupuestos_acepta_una_prestacion_inactiva_del_tenant(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """Borde R11: el adaptador resuelve por id del tenant aunque la prestación esté inactiva."""
    prestacion = await _prestacion(session, tenant_a, nombre="Prestación discontinuada")
    prestacion.activa = False
    await session.flush()
    await _convenio(session, tenant_a, prestacion, arancel="10000.00")

    precio_unit, cobertura, a_cargo = await calcular_montos_item_presupuesto(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prestacion.id,
        cantidad=1,
        obra_social="OSDE",
        fecha_referencia=FECHA,
    )

    assert (precio_unit, cobertura, a_cargo) == (
        Decimal("50000.00"),
        Decimal("10000.00"),
        Decimal("40000.00"),
    )
    guardadas = (
        (await session.execute(select(Prestacion).where(Prestacion.id == prestacion.id)))
        .scalars()
        .all()
    )
    assert len(guardadas) == 1
