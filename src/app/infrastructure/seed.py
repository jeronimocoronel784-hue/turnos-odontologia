"""Seed piloto idempotente: 1 tenant + 1 Dueño + permisos base (spec 2.5, R13).

Datos 100% ficticios e identificables como tales. Re-ejecutable sin duplicar
(upsert por slug/email). Corre con el rol owner (DDL/seed), no con el rol app.
"""

import hashlib
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
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


def _hash_dev(password: str) -> str:
    """Hash de desarrollo (pbkdf2 stdlib). C-03 define el esquema auth final."""
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), sal.encode(), 100_000).hex()
    return f"pbkdf2_sha256$100000${sal}${digest}"


async def ejecutar_seed(session: AsyncSession) -> dict[str, int]:
    """Ejecuta el seed. Devuelve conteos {tenants, usuarios} finales."""
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
    await session.commit()

    n_tenants = (await session.execute(select(func.count()).select_from(Tenant))).scalar_one()
    n_duenos = (
        await session.execute(
            select(func.count()).select_from(Usuario).where(Usuario.rol == RolUsuario.DUENO)
        )
    ).scalar_one()
    return {"tenants": int(n_tenants), "duenos": int(n_duenos)}


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
