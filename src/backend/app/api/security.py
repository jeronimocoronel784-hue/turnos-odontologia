"""Autenticación y autorización de requests (C-03, R4).

`actor_actual` resuelve la identidad desde el access token y revalida contra la
DB (usuario activo y mismo tenant). `requiere` aplica la matriz RBAC y devuelve
403 sin revelar si el recurso existe.
"""

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.domain.rbac import Accion, Recurso, permite
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.jwt import decodificar_access
from app.shared.exceptions import NoAutenticado, PermisoInsuficiente
from app.shared.settings import Settings


@dataclass(frozen=True)
class ActorAutenticado:
    """Identidad efectiva del request: el `tenant_id` sale SIEMPRE del token."""

    usuario_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    nombre: str
    roles: tuple[RolUsuario, ...]


def _token_del_header(request: Request) -> str:
    esquema, _, token = request.headers.get("Authorization", "").partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        raise NoAutenticado()
    return token.strip()


def _uuid_claim(claims: dict[str, Any], clave: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(claims[clave]))
    except (KeyError, ValueError) as exc:
        raise NoAutenticado() from exc


async def actor_actual(
    request: Request,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
) -> ActorAutenticado:
    """Valida el access token y confirma que el usuario sigue activo en su tenant."""
    claims = decodificar_access(_token_del_header(request), settings)
    usuario_id = _uuid_claim(claims, "sub")
    tenant_id = _uuid_claim(claims, "tenant_id")

    usuario = await session.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo or usuario.tenant_id != tenant_id:
        raise NoAutenticado()

    return ActorAutenticado(
        usuario_id=usuario.id,
        tenant_id=usuario.tenant_id,
        email=usuario.email,
        nombre=usuario.nombre,
        roles=(RolUsuario(usuario.rol),),
    )


DependenciaGuard = Callable[..., Coroutine[Any, Any, ActorAutenticado]]


def requiere(recurso: Recurso, accion: Accion) -> DependenciaGuard:
    """Dependency factory: exige que algún rol del actor tenga la acción sobre el recurso."""

    async def _guard(
        actor: Annotated[ActorAutenticado, Depends(actor_actual)],
    ) -> ActorAutenticado:
        if not permite((rol.value for rol in actor.roles), recurso, accion):
            raise PermisoInsuficiente()
        return actor

    return _guard
