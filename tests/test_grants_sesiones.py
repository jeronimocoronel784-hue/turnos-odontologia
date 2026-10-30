"""GRANTs de la migración 002: el rol app hace CRUD en sesiones y tokens (tarea 1.2).

Requiere `APP_ROLE_URL_TEST` apuntando al rol restringido sobre Postgres (en CI y
en el entorno local del piloto). Sin esa variable no hay forma de probar permisos
de DB; el caso se reporta como verificación pendiente.
"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.tenant import Tenant
from app.domain.usuario import Usuario
from app.shared.database import create_engine_for


def _factory_rol_app() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("APP_ROLE_URL_TEST", "")
    if not url:
        pytest.skip(
            "Falta APP_ROLE_URL_TEST (rol app restringido en Postgres); pendiente sin Docker."
        )
    return async_sessionmaker(create_engine_for(url), class_=AsyncSession, expire_on_commit=False)


async def test_el_rol_app_puede_hacer_crud_en_sesiones_y_tokens(
    session: AsyncSession, dialecto: str, tenant_a: Tenant, crear_usuario
) -> None:
    if dialecto != "postgresql":
        pytest.skip("Los GRANTs por rol solo existen en Postgres.")
    usuario: Usuario = await crear_usuario(tenant_a, email="grants@example.com")
    await session.commit()

    factory = _factory_rol_app()
    refresh_id = uuid.uuid4()
    gestion_id = uuid.uuid4()
    async with factory() as app_session:
        actual = (await app_session.execute(text("SELECT current_user"))).scalar_one()
        assert actual == "turnos_app"

        privilegios = (
            (
                await app_session.execute(
                    text(
                        "SELECT has_table_privilege('turnos_app','refresh_token','INSERT') AS ri,"
                        " has_table_privilege('turnos_app','refresh_token','SELECT') AS rs,"
                        " has_table_privilege('turnos_app','refresh_token','UPDATE') AS ru,"
                        " has_table_privilege('turnos_app','refresh_token','DELETE') AS rd,"
                        " has_table_privilege('turnos_app','token_gestion','INSERT') AS gi,"
                        " has_table_privilege('turnos_app','token_gestion','SELECT') AS gs,"
                        " has_table_privilege('turnos_app','token_gestion','UPDATE') AS gu,"
                        " has_table_privilege('turnos_app','token_gestion','DELETE') AS gd"
                    )
                )
            )
            .mappings()
            .one()
        )
        assert all(privilegios.values()), privilegios

        await app_session.execute(
            text(
                "INSERT INTO refresh_token (id, tenant_id, usuario_id, token_hash, familia_id,"
                " vence_at, revocado_at, reemplazado_por_id, created_at)"
                " VALUES (:id, :tenant, :usuario, :hash, :familia, now() + interval '1 day',"
                " NULL, NULL, now())"
            ),
            {
                "id": refresh_id.hex,
                "tenant": tenant_a.id.hex,
                "usuario": usuario.id.hex,
                "hash": "a" * 64,
                "familia": uuid.uuid4().hex,
            },
        )
        await app_session.execute(
            text(
                "INSERT INTO token_gestion (id, tenant_id, recurso, recurso_id, token_hash,"
                " vence_at, revocado_at, usado_at, created_at)"
                " VALUES (:id, :tenant, 'turno', 'turno-1', :hash,"
                " now() + interval '1 day', NULL, NULL, now())"
            ),
            {"id": gestion_id.hex, "tenant": tenant_a.id.hex, "hash": "b" * 64},
        )
        await app_session.execute(
            text("UPDATE refresh_token SET revocado_at = now() WHERE id = :id"),
            {"id": refresh_id.hex},
        )
        await app_session.execute(
            text("UPDATE token_gestion SET usado_at = now() WHERE id = :id"),
            {"id": gestion_id.hex},
        )
        assert (
            await app_session.execute(
                text("SELECT revocado_at FROM refresh_token WHERE id = :id"),
                {"id": refresh_id.hex},
            )
        ).scalar_one() is not None

        await app_session.execute(
            text("DELETE FROM token_gestion WHERE id = :id"), {"id": gestion_id.hex}
        )
        await app_session.execute(
            text("DELETE FROM refresh_token WHERE id = :id"), {"id": refresh_id.hex}
        )
        await app_session.commit()
