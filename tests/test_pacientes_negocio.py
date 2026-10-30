"""Tests de lógica de negocio y casos de uso de pacientes (tarea 2.2).

Verifica:
- get_or_create_paciente para reserva pública sin login.
- Unicidad de DNI por consultorio (aislamiento multi-tenant).
- Inicialización atómica de FichaClinica 1:1.
- RN-CO-01: Bloqueo de WhatsApp automático si optin_wa = False.
- RN-CO-01: Baja STOP que corta envíos inmediatamente.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.pacientes import get_or_create_paciente, procesar_baja_stop
from app.domain.auditoria import Auditoria
from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente, puede_enviar_whatsapp
from app.domain.tenant import Tenant


@pytest.mark.asyncio
async def test_get_or_create_paciente_nuevo_crea_paciente_y_ficha(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    paciente, creado = await get_or_create_paciente(
        session,
        tenant_id=tenant_a.id,
        nombre="Laura Pausini",
        dni=" 42.999.888 ",
        telefono="11 5566 7788",
        email="laura@test.com",
    )
    assert creado is True
    assert paciente.nombre == "Laura Pausini"
    assert paciente.dni == "42999888"
    assert paciente.telefono == "11 5566 7788"
    assert paciente.optin_wa is False  # RN-CO-01: default False
    assert paciente.activo is True

    # Verificar que FichaClinica se creó en DB
    stmt = select(FichaClinica).where(FichaClinica.paciente_id == paciente.id)
    res = await session.execute(stmt)
    ficha = res.scalar_one_or_none()
    assert ficha is not None
    assert ficha.tenant_id == tenant_a.id


@pytest.mark.asyncio
async def test_get_or_create_paciente_existente_actualiza_contacto_sin_duplicar(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    # Primera vez: alta
    p1, creado1 = await get_or_create_paciente(
        session,
        tenant_id=tenant_a.id,
        nombre="Diego Maradona",
        dni="10101010",
        telefono="1100101010",
    )
    assert creado1 is True

    # Segunda vez: mismo DNI con formato distinto y nuevo teléfono
    p2, creado2 = await get_or_create_paciente(
        session,
        tenant_id=tenant_a.id,
        nombre="Diego Armando Maradona",
        dni="10.101.010",
        telefono="1199998888",
    )
    assert creado2 is False
    assert p2.id == p1.id
    assert p2.nombre == "Diego Armando Maradona"
    assert p2.telefono == "1199998888"

    # Verificar que en la DB hay exactamente 1 paciente con ese DNI
    stmt = select(Paciente).where(Paciente.tenant_id == tenant_a.id, Paciente.dni == "10101010")
    res = await session.execute(stmt)
    pacientes = res.scalars().all()
    assert len(pacientes) == 1


@pytest.mark.asyncio
async def test_get_or_create_mismo_dni_distinto_tenant_crea_ambos(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    # Paciente con mismo DNI en tenant A y tenant B
    pa, creado_a = await get_or_create_paciente(
        session,
        tenant_id=tenant_a.id,
        nombre="Paciente Compartido A",
        dni="33444555",
        telefono="11111111",
    )
    pb, creado_b = await get_or_create_paciente(
        session,
        tenant_id=tenant_b.id,
        nombre="Paciente Compartido B",
        dni="33444555",
        telefono="22222222",
    )

    assert creado_a is True
    assert creado_b is True
    assert pa.id != pb.id
    assert pa.tenant_id == tenant_a.id
    assert pb.tenant_id == tenant_b.id


@pytest.mark.asyncio
async def test_rn_co_01_bloqueo_envios_y_baja_stop(session: AsyncSession, tenant_a: Tenant) -> None:
    paciente, _ = await get_or_create_paciente(
        session,
        tenant_id=tenant_a.id,
        nombre="Usuario WhatsApp",
        dni="50111222",
        telefono="1122334455",
    )

    # 1. Sin opt-in: el envío automático está bloqueado
    assert puede_enviar_whatsapp(paciente) is False

    # 2. El usuario acepta opt-in
    paciente.optin_wa = True
    await session.flush()
    assert puede_enviar_whatsapp(paciente) is True

    # 3. Paciente envía 'STOP' -> se procesa la baja
    await procesar_baja_stop(session, paciente)
    assert paciente.optin_wa is False

    # 4. Los envíos automáticos quedan inmediatamente bloqueados
    assert puede_enviar_whatsapp(paciente) is False

    # 5. Se verifica registro de auditoría de la baja STOP
    stmt = select(Auditoria).where(
        Auditoria.entidad_id == str(paciente.id),
        Auditoria.accion == "paciente.baja_stop",
    )
    res = await session.execute(stmt)
    evento = res.scalar_one_or_none()
    assert evento is not None
    assert evento.despues == {"optin_wa": False}
