"""Seed piloto: en vacía crea 1 tenant + 1 Dueño + 1 Sillón + 5 prestaciones.

Re-ejecutar no duplica registros (spec 2.5, C-04).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.seed import PERMISOS_BASE, ejecutar_seed


async def test_seed_en_base_vacia_crea_tenant_dueno_y_catalogo(
    session: AsyncSession,
) -> None:
    resultado = await ejecutar_seed(session)
    assert resultado == {"tenants": 1, "duenos": 1, "sillones": 1, "prestaciones": 5}

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

    # Sillón Box 1
    sillon = (await session.execute(select(Sillon))).scalar_one()
    assert sillon.tenant_id == tenant.id
    assert sillon.nombre == "Box 1"
    assert sillon.sucursal == "central"
    assert sillon.activo is True

    # 5 Prestaciones base
    prestaciones = list(
        (await session.execute(select(Prestacion).order_by(Prestacion.nombre))).scalars().all()
    )
    assert len(prestaciones) == 5
    nombres = {p.nombre for p in prestaciones}
    assert nombres == {"Limpieza", "Consulta", "Arreglo", "Endodoncia", "Extracción"}

    # Endodoncia y Extracción requieren seña y son invasivas
    endodoncia = next(p for p in prestaciones if p.nombre == "Endodoncia")
    assert endodoncia.requiere_sena is True
    assert endodoncia.monto_sena is not None and endodoncia.monto_sena > 0
    assert endodoncia.invasiva is True


async def test_seed_doble_ejecucion_no_duplica(session: AsyncSession) -> None:
    primero = await ejecutar_seed(session)
    segundo = await ejecutar_seed(session)
    assert primero == segundo == {"tenants": 1, "duenos": 1, "sillones": 1, "prestaciones": 5}

    n_usuarios = (await session.execute(select(func.count()).select_from(Usuario))).scalar_one()
    assert n_usuarios == 1

    n_sillones = (await session.execute(select(func.count()).select_from(Sillon))).scalar_one()
    assert n_sillones == 1

    n_prestaciones = (
        await session.execute(select(func.count()).select_from(Prestacion))
    ).scalar_one()
    assert n_prestaciones == 5


async def test_seed_prestaciones_tienen_duracion_y_precios_validos(
    session: AsyncSession,
) -> None:
    await ejecutar_seed(session)
    prestaciones = list((await session.execute(select(Prestacion))).scalars().all())
    for p in prestaciones:
        assert p.duracion_min > 0
        assert p.precio_particular >= 0
        if p.requiere_sena:
            assert p.monto_sena is not None and p.monto_sena > 0
