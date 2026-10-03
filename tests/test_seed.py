"""Seed piloto: en vacía crea 1 tenant + 1 Dueño; re-ejecutar no duplica (spec 2.5)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.seed import PERMISOS_BASE, ejecutar_seed


async def test_seed_en_base_vacia_crea_tenant_y_dueno_ficticios(session: AsyncSession) -> None:
    resultado = await ejecutar_seed(session)
    assert resultado == {"tenants": 1, "duenos": 1}

    tenant = (await session.execute(select(Tenant))).scalar_one()
    assert tenant.slug == "consultorio-piloto"
    assert "ficticio" in tenant.nombre.lower()

    dueno = (
        await session.execute(select(Usuario).where(Usuario.rol == RolUsuario.DUENO))
    ).scalar_one()
    assert dueno.tenant_id == tenant.id
    assert dueno.activo is True
    assert "fictic" in dueno.nombre.lower() or "piloto" in dueno.nombre.lower()
    assert set(PERMISOS_BASE) == {"dueno", "recepcion", "odontologo"}


async def test_seed_doble_ejecucion_no_duplica(session: AsyncSession) -> None:
    primero = await ejecutar_seed(session)
    segundo = await ejecutar_seed(session)
    assert primero == segundo == {"tenants": 1, "duenos": 1}
    n_usuarios = (await session.execute(select(func.count()).select_from(Usuario))).scalar_one()
    assert n_usuarios == 1
