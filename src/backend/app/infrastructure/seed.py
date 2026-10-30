"""Seed piloto idempotente: 1 tenant + 1 Dueño + 1 Sillón + 5 prestaciones (spec 2.5, C-04, R13).

Datos 100% ficticios e identificables como tales. Re-ejecutable sin duplicar
(upsert por slug/email/nombre). Corre con el rol owner (DDL/seed), no con el rol app.
"""

import hashlib
import secrets
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario

# Matriz de permisos base por rol (RBAC v1, matriz §03; enforced en API desde C-03).
PERMISOS_BASE: dict[str, list[str]] = {
    RolUsuario.DUENO.value: ["*"],
    RolUsuario.RECEPCION.value: [
        "turnos:crear",
        "turnos:ver",
        "turnos:confirmar",
        "pacientes:crear",
        "pacientes:ver",
        "caja:cobrar",
    ],
    RolUsuario.ODONTOLOGO.value: [
        "agenda:ver",
        "hc:ver",
        "hc:evolucionar",
        "odontograma:editar",
    ],
}

POLITICAS_SEED: dict[str, int] = {
    "anticipacion_min_dias": 1,
    "sena_default_pct": 30,
    "cancelacion_horas": 24,
}
TENANT_SEED = {
    "slug": "consultorio-piloto",
    "nombre": "Consultorio Piloto Sonría (ficticio)",
}
DUENO_SEED = {
    "email": "duena.piloto@example.com",
    "nombre": "Dueña Piloto Ficticia",
}

SILLON_SEED = {
    "nombre": "Box 1",
    "sucursal": "central",
}

PRESTACIONES_SEED = [
    {
        "nombre": "Limpieza",
        "duracion_min": 30,
        "precio_particular": Decimal("15000.00"),
        "requiere_sena": False,
        "monto_sena": None,
        "invasiva": False,
    },
    {
        "nombre": "Consulta",
        "duracion_min": 20,
        "precio_particular": Decimal("10000.00"),
        "requiere_sena": False,
        "monto_sena": None,
        "invasiva": False,
    },
    {
        "nombre": "Arreglo",
        "duracion_min": 45,
        "precio_particular": Decimal("25000.00"),
        "requiere_sena": False,
        "monto_sena": None,
        "invasiva": False,
    },
    {
        "nombre": "Endodoncia",
        "duracion_min": 60,
        "precio_particular": Decimal("50000.00"),
        "requiere_sena": True,
        "monto_sena": Decimal("15000.00"),
        "invasiva": True,
    },
    {
        "nombre": "Extracción",
        "duracion_min": 45,
        "precio_particular": Decimal("35000.00"),
        "requiere_sena": True,
        "monto_sena": Decimal("10000.00"),
        "invasiva": True,
    },
]


def _hash_dev(password: str) -> str:
    """Hash de desarrollo (pbkdf2 stdlib). C-03 define el esquema auth final."""
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), sal.encode(), 100_000).hex()
    return f"pbkdf2_sha256$100000${sal}${digest}"


async def ejecutar_seed(session: AsyncSession) -> dict[str, int]:
    """Ejecuta el seed piloto. Devuelve conteos {tenants, duenos, sillones, prestaciones}."""
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == TENANT_SEED["slug"]))
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            id=uuid.uuid4(),
            slug=TENANT_SEED["slug"],
            nombre=TENANT_SEED["nombre"],
            politicas=dict(POLITICAS_SEED),
            activo=True,
        )
        session.add(tenant)
        await session.flush()

    dueno = (
        await session.execute(
            select(Usuario).where(
                Usuario.tenant_id == tenant.id, Usuario.email == DUENO_SEED["email"]
            )
        )
    ).scalar_one_or_none()
    if dueno is None:
        dueno = Usuario(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=DUENO_SEED["email"],
            nombre=DUENO_SEED["nombre"],
            rol=RolUsuario.DUENO,
            matricula=None,
            password_hash=_hash_dev(secrets.token_urlsafe(24)),
            activo=True,
        )
        session.add(dueno)
        await session.flush()
        session.add(
            Auditoria(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                actor_id=dueno.id,
                accion="seed.inicial",
                entidad="tenant",
                entidad_id=str(tenant.id),
                antes=None,
                despues={"slug": tenant.slug, "permisos_base": PERMISOS_BASE},
            )
        )

    # 1. Sillón Box 1
    sillon = (
        await session.execute(
            select(Sillon).where(
                Sillon.tenant_id == tenant.id,
                Sillon.sucursal == SILLON_SEED["sucursal"],
                Sillon.nombre == SILLON_SEED["nombre"],
            )
        )
    ).scalar_one_or_none()
    if sillon is None:
        sillon = Sillon(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            nombre=SILLON_SEED["nombre"],
            sucursal=SILLON_SEED["sucursal"],
            activo=True,
        )
        session.add(sillon)
        await session.flush()

    # 2. 5 prestaciones base
    for p_seed in PRESTACIONES_SEED:
        prestacion = (
            await session.execute(
                select(Prestacion).where(
                    Prestacion.tenant_id == tenant.id,
                    Prestacion.nombre == p_seed["nombre"],
                )
            )
        ).scalar_one_or_none()
        if prestacion is None:
            prestacion = Prestacion(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                nombre=str(p_seed["nombre"]),
                duracion_min=int(p_seed["duracion_min"]),  # type: ignore[call-overload]
                precio_particular=Decimal(str(p_seed["precio_particular"])),
                requiere_sena=bool(p_seed["requiere_sena"]),
                monto_sena=Decimal(str(p_seed["monto_sena"])) if p_seed["monto_sena"] else None,
                invasiva=bool(p_seed["invasiva"]),
                activa=True,
            )
            session.add(prestacion)
    await session.flush()
    await session.commit()

    n_tenants = (await session.execute(select(func.count()).select_from(Tenant))).scalar_one()
    n_duenos = (
        await session.execute(
            select(func.count()).select_from(Usuario).where(Usuario.rol == RolUsuario.DUENO)
        )
    ).scalar_one()
    n_sillones = (await session.execute(select(func.count()).select_from(Sillon))).scalar_one()
    n_prestaciones = (
        await session.execute(select(func.count()).select_from(Prestacion))
    ).scalar_one()
    return {
        "tenants": int(n_tenants),
        "duenos": int(n_duenos),
        "sillones": int(n_sillones),
        "prestaciones": int(n_prestaciones),
    }


async def _cli() -> None:

    from app.shared.database import session_factory_for
    from app.shared.settings import get_settings

    factory = session_factory_for(get_settings().database_url)
    async with factory() as session:
        resultado = await ejecutar_seed(session)
    print(resultado)


if __name__ == "__main__":
    import asyncio

    asyncio.run(_cli())
