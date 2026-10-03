"""Aislamiento por tenant: A nunca ve filas de B; sin contexto no hay datos (CRITICAL, spec 2.3)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.repository import BaseRepository, TenantContextoRequerido
from app.infrastructure.db.unit_of_work import usar_uow


def _repo(session: AsyncSession, tenant: Tenant) -> BaseRepository[Usuario]:
    return BaseRepository(session, tenant.id, Usuario)


async def test_tenant_a_no_ve_usuarios_del_tenant_b(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    async with usar_uow(session, tenant_a.id) as uow:
        await uow.repos(Usuario).agregar(
            Usuario(
                id=uuid.uuid4(),
                email="solo-a@example.com",
                nombre="Solo A",
                rol=RolUsuario.RECEPCION,
                password_hash="x",
                activo=True,
            )
        )
    async with usar_uow(session, tenant_b.id) as uow:
        await uow.repos(Usuario).agregar(
            Usuario(
                id=uuid.uuid4(),
                email="solo-b@example.com",
                nombre="Solo B",
                rol=RolUsuario.RECEPCION,
                password_hash="x",
                activo=True,
            )
        )

    vistos_a = await _repo(session, tenant_a).listar()
    vistos_b = await _repo(session, tenant_b).listar()
    assert {u.email for u in vistos_a} == {"solo-a@example.com"}
    assert {u.email for u in vistos_b} == {"solo-b@example.com"}

    otro = next(u for u in vistos_b if u.email == "solo-b@example.com")
    assert await _repo(session, tenant_a).obtener(otro.id) is None


async def test_consulta_sin_tenant_se_niega_en_vez_de_filtrar_mal(session: AsyncSession) -> None:
    with pytest.raises(TenantContextoRequerido):
        BaseRepository(session, None, Usuario)


async def test_agregar_con_tenant_ajeno_se_rechaza(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    intruso = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        email="intruso@example.com",
        nombre="Intruso",
        rol=RolUsuario.RECEPCION,
        password_hash="x",
        activo=True,
    )
    with pytest.raises(TenantContextoRequerido):
        await _repo(session, tenant_a).agregar(intruso)
    await session.rollback()
