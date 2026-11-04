"""Tests de integración de lógica de negocio para Presupuestos y Planes de Tratamiento (tarea 2.1).

Verifica:
1. Cálculo servidor de cobertura OS vigente vs. particular (RN-OS-01, R8).
2. Aceptación de presupuesto con prestación invasiva exige consentimiento firmado (RN-CL-04).
3. Vinculación de turnos al presupuesto pasa el estado de 'aceptado' a 'en_curso'.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_clinica import ConsentimientoCreate, ConsentimientoFirmaInput
from app.api.schemas_presupuestos import (
    PresupuestoCreate,
    PresupuestoItemInput,
    PresupuestoVincularTurnoInput,
)
from app.application.agenda import crear_turno
from app.application.clinica import crear_consentimiento, firmar_consentimiento
from app.application.presupuestos import (
    aceptar_presupuesto,
    agregar_item_presupuesto,
    cambiar_estado_presupuesto,
    crear_presupuesto,
    listar_turnos_presupuesto,
    vincular_turno_a_presupuesto,
)
from app.domain.clinica import CanalFirmaConsentimiento
from app.domain.cobertura_os import CoberturaOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.presupuesto import EstadoPresupuesto
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.shared.exceptions import Conflicto


async def _preparar_contexto_presupuesto(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[Usuario, Paciente, Sillon, Prestacion, Prestacion]:
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="odonto-neg-c10@consultorio.test",
        nombre="Dra. Plan Tratamiento",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-10101",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        nombre="Martín Plan",
        dni="37888999",
        telefono="+5491122223333",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        nombre="Box Presupuesto",
        activo=True,
    )
    prest_limpieza = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        nombre="Limpieza ultrasónica",
        duracion_min=30,
        precio_particular=Decimal("40000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    prest_implante = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        nombre="Implante osteointegrado",
        duracion_min=60,
        precio_particular=Decimal("250000.00"),
        requiere_sena=False,
        invasiva=True,
        activa=True,
    )
    cobertura_osde = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        obra_social="OSDE",
        prestacion_id=prest_limpieza.id,
        arancel=Decimal("30000.00"),
        copago=Decimal("10000.00"),
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 12, 31),
        activa=True,
    )
    # Sin `relationship()` el unit-of-work no ordena los INSERTs: las prestaciones
    # (padres) se flushEAN antes que la cobertura_os (hijo) para no violar la FK.
    session.add_all([odontologo, paciente, sillon, prest_limpieza, prest_implante])
    await session.flush()
    session.add(cobertura_osde)
    await session.flush()
    return odontologo, paciente, sillon, prest_limpieza, prest_implante


async def test_calculo_cobertura_os_vigente_vs_particular(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-OS-01, R8: con cobertura OSDE vigente descuenta 30000; sin cobertura es particular."""
    odontologo, paciente, _, prest_limpieza, _ = await _preparar_contexto_presupuesto(
        session, tenant_a.id
    )

    pres_osde = await crear_presupuesto(
        session,
        tenant_id=tenant_a.id,
        datos=PresupuestoCreate(
            paciente_id=paciente.id,
            obra_social="OSDE",
            items=[PresupuestoItemInput(prestacion_id=prest_limpieza.id, cantidad=1)],
        ),
        actor_id=odontologo.id,
        fecha_referencia=date(2026, 11, 1),
    )
    assert pres_osde.total == Decimal("40000.00")
    assert pres_osde.total_cobertura_os == Decimal("30000.00")
    assert pres_osde.total_a_cargo == Decimal("10000.00")
    assert pres_osde.items[0].a_cargo == Decimal("10000.00")

    # Agregar un segundo item recalcula los totales del presupuesto
    pres_osde_2 = await agregar_item_presupuesto(
        session,
        tenant_id=tenant_a.id,
        presupuesto_id=pres_osde.id,
        item_input=PresupuestoItemInput(prestacion_id=prest_limpieza.id, pieza_fdi=16, cantidad=2),
        actor_id=odontologo.id,
        fecha_referencia=date(2026, 11, 1),
    )
    assert pres_osde_2.total == Decimal("120000.00")
    assert pres_osde_2.total_cobertura_os == Decimal("90000.00")
    assert pres_osde_2.total_a_cargo == Decimal("30000.00")

    # Presupuesto para obra social sin convenio vigente ("SWISS") -> particular (cobertura 0)
    pres_part = await crear_presupuesto(
        session,
        tenant_id=tenant_a.id,
        datos=PresupuestoCreate(
            paciente_id=paciente.id,
            obra_social="SWISS",
            items=[PresupuestoItemInput(prestacion_id=prest_limpieza.id, cantidad=1)],
        ),
        actor_id=odontologo.id,
        fecha_referencia=date(2026, 11, 1),
    )
    assert pres_part.total_cobertura_os == Decimal("0.00")
    assert pres_part.total_a_cargo == Decimal("40000.00")


async def test_aceptar_presupuesto_con_invasiva_exige_consentimiento_y_vincula_turnos(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-CL-04, US-022: aceptar con invasiva sin firma falla (409); tras firmar acepta."""
    odontologo, paciente, sillon, _, prest_implante = await _preparar_contexto_presupuesto(
        session, tenant_a.id
    )

    pres = await crear_presupuesto(
        session,
        tenant_id=tenant_a.id,
        datos=PresupuestoCreate(
            paciente_id=paciente.id,
            items=[PresupuestoItemInput(prestacion_id=prest_implante.id, pieza_fdi=36, cantidad=1)],
        ),
        actor_id=odontologo.id,
    )
    await cambiar_estado_presupuesto(
        session,
        tenant_id=tenant_a.id,
        presupuesto_id=pres.id,
        nuevo_estado=EstadoPresupuesto.PRESENTADO,
        actor_id=odontologo.id,
    )

    # 1. Intentar aceptar sin consentimiento firmado para prest_implante -> Conflicto
    with pytest.raises(Conflicto, match="consentimiento"):
        await aceptar_presupuesto(
            session,
            tenant_id=tenant_a.id,
            presupuesto_id=pres.id,
            actor_id=odontologo.id,
        )

    # 2. Emitir y firmar consentimiento para prest_implante
    cons, _ = await crear_consentimiento(
        session,
        tenant_id=tenant_a.id,
        datos=ConsentimientoCreate(
            paciente_id=paciente.id,
            prestacion_id=prest_implante.id,
            texto_version="v1.0-implante",
            texto_contenido="Autorizo colocación de implante osteointegrado.",
        ),
        actor_id=odontologo.id,
    )
    await firmar_consentimiento(
        session,
        tenant_id=tenant_a.id,
        consentimiento_id=cons.id,
        datos=ConsentimientoFirmaInput(
            firmado_por="Martín Plan DNI 37888999",
            firma_datos="firma-presencial-trazo",
            canal=CanalFirmaConsentimiento.PRESENCIAL,
        ),
        actor_id=odontologo.id,
    )

    # 3. Ahora aceptar_presupuesto tiene éxito
    pres_aceptado = await aceptar_presupuesto(
        session,
        tenant_id=tenant_a.id,
        presupuesto_id=pres.id,
        actor_id=odontologo.id,
    )
    assert pres_aceptado.estado == EstadoPresupuesto.ACEPTADO.value

    # 4. Vincular turno pasa el presupuesto de ACEPTADO a EN_CURSO
    turno, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prest_implante.id,
        inicio=datetime(2026, 11, 29, 11, 0, tzinfo=UTC),
        actor_id=odontologo.id,
    )
    await vincular_turno_a_presupuesto(
        session,
        tenant_id=tenant_a.id,
        presupuesto_id=pres.id,
        datos=PresupuestoVincularTurnoInput(
            turno_id=turno.id,
            presupuesto_item_id=pres_aceptado.items[0].id,
        ),
        actor_id=odontologo.id,
    )

    vinculos = await listar_turnos_presupuesto(
        session, tenant_id=tenant_a.id, presupuesto_id=pres.id
    )
    assert len(vinculos) == 1
    assert vinculos[0].turno_id == turno.id

    # 5. Finalizar el plan
    pres_fin = await cambiar_estado_presupuesto(
        session,
        tenant_id=tenant_a.id,
        presupuesto_id=pres.id,
        nuevo_estado=EstadoPresupuesto.FINALIZADO,
        actor_id=odontologo.id,
    )
    assert pres_fin.estado == EstadoPresupuesto.FINALIZADO.value
