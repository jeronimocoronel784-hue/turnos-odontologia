"""Modelos core: alta feliz, unicidad por tenant, matrícula según rol (spec 2.1)."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import UsuarioCreate
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.errors import error_integridad


async def _crear_usuario(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    email: str = "recepcion@example.com",
    rol: RolUsuario = RolUsuario.RECEPCION,
    matricula: str | None = None,
) -> Usuario:
    usuario = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=email,
        nombre="Usuaria Test",
        rol=rol,
        matricula=matricula,
        password_hash="hash-ficticio",
        activo=True,
    )
    session.add(usuario)
    await session.flush()
    return usuario


async def test_alta_feliz_recepcionista_sin_matricula(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    usuaria = await _crear_usuario(session, tenant_a.id)
    assert usuaria.id is not None
    assert usuaria.rol == RolUsuario.RECEPCION
    assert usuaria.tenant_id == tenant_a.id


async def test_email_duplicado_mismo_tenant_se_rechaza(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    await _crear_usuario(session, tenant_a.id, email="recepcion@ejemplo.com")
    with pytest.raises(IntegrityError):
        await _crear_usuario(session, tenant_a.id, email="recepcion@ejemplo.com")
    await session.rollback()
    # El mensaje que verá el usuario es rioplatense e indica qué hacer.
    err = error_integridad("email_duplicado")
    assert err.status_code == 409
    assert "ya está en uso" in err.mensaje


async def test_mismo_email_en_otro_tenant_esta_permitido(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    await _crear_usuario(session, tenant_a.id, email="recepcion@ejemplo.com")
    otro = await _crear_usuario(session, tenant_b.id, email="recepcion@ejemplo.com")
    assert otro.tenant_id == tenant_b.id


async def test_odontologo_sin_matricula_se_rechaza_en_schema_y_en_db(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    with pytest.raises(ValidationError) as info:
        UsuarioCreate(
            email="odonto@example.com",
            nombre="Odonto Test",
            rol=RolUsuario.ODONTOLOGO,
            password="contrasena123",
        )
    assert "matrícula" in str(info.value)

    with pytest.raises(IntegrityError):
        await _crear_usuario(
            session, tenant_a.id, email="odonto@example.com", rol=RolUsuario.ODONTOLOGO
        )
    await session.rollback()


async def test_slug_duplicado_de_tenant_se_rechaza(session: AsyncSession, tenant_a: Tenant) -> None:
    session.add(
        Tenant(id=uuid.uuid4(), slug=tenant_a.slug, nombre="Otro", politicas={}, activo=True)
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
    assert "ya existe" in error_integridad("slug_duplicado").mensaje
