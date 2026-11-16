"""Utilería idempotente para crear o actualizar el usuario de demo (C-18).

Crea o actualiza el usuario ficticio `demo.piloto@example.com` en el tenant
`consultorio-piloto` (rol `recepcion`) con hash bcrypt generado por `hashear_password`
a partir de la variable de entorno `DEMO_PASSWORD` (R10, R13).
"""

import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.passwords import hashear_password
from app.infrastructure.seed import TENANT_SEED

EMAIL_DEMO: str = "demo.piloto@example.com"
NOMBRE_DEMO: str = "Recepción Demo Ficticia"


def _validar_demo_password(demo_password: str | None) -> str:
    valor = (demo_password if demo_password is not None else os.getenv("DEMO_PASSWORD", "")).strip()
    if not valor:
        raise RuntimeError(
            "Che, falta configurar la variable de entorno DEMO_PASSWORD para crear el usuario demo."
        )
    return valor


async def upsert_usuario_demo(
    session: AsyncSession,
    *,
    demo_password: str | None = None,
    bcrypt_rounds: int = 4,
) -> Usuario:
    """Hace upsert idempotente del usuario demo en el tenant `consultorio-piloto`."""
    pwd_limpio = _validar_demo_password(demo_password)

    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == TENANT_SEED["slug"]))
    ).scalar_one_or_none()
    if tenant is None:
        raise RuntimeError(
            f"Che, no encontramos el consultorio '{TENANT_SEED['slug']}'. Corré el seed primero."
        )

    usuario = (
        await session.execute(
            select(Usuario).where(
                Usuario.tenant_id == tenant.id,
                Usuario.email == EMAIL_DEMO,
            )
        )
    ).scalar_one_or_none()

    hash_bcrypt = hashear_password(pwd_limpio, bcrypt_rounds)

    if usuario is None:
        usuario = Usuario(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=EMAIL_DEMO,
            nombre=NOMBRE_DEMO,
            rol=RolUsuario.RECEPCION,
            matricula=None,
            password_hash=hash_bcrypt,
            activo=True,
        )
        session.add(usuario)
    else:
        usuario.nombre = NOMBRE_DEMO
        usuario.rol = RolUsuario.RECEPCION
        usuario.password_hash = hash_bcrypt
        usuario.activo = True

    await session.flush()
    return usuario


def ejecutar_usuario_demo_cli(demo_password: str | None = None) -> dict[str, str]:
    """Punto de entrada sincrónico que valida `DEMO_PASSWORD` y ejecuta el upsert."""
    pwd = _validar_demo_password(demo_password)

    async def _run() -> dict[str, str]:
        from app.shared.database import session_factory_for
        from app.shared.settings import get_settings

        settings = get_settings()
        dsn = settings.database_url_owner or settings.database_url
        factory = session_factory_for(dsn)
        async with factory() as session:
            u = await upsert_usuario_demo(
                session,
                demo_password=pwd,
                bcrypt_rounds=settings.bcrypt_rounds,
            )
            await session.commit()
            return {"email": u.email, "rol": str(u.rol), "tenant_id": str(u.tenant_id)}

    return asyncio.run(_run())


if __name__ == "__main__":
    resultado = ejecutar_usuario_demo_cli()
    print(resultado)
