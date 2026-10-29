"""Endpoints de autenticación: login, refresh, logout y me (C-03, D2/D3)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_auth import IdentidadRead, LoginRequest, TokenResponse
from app.api.security import ActorAutenticado, actor_actual
from app.application.auth.sesiones import (
    abrir_sesion,
    autenticar,
    cerrar_sesion,
    rotar_refresh,
)
from app.domain.tenant import Tenant
from app.domain.usuario import Usuario
from app.infrastructure.security.rate_limit import ClienteRedis, verificar_limite_login
from app.shared.exceptions import NoAutenticado
from app.shared.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])

NOMBRE_COOKIE = "refresh_token"
RUTA_COOKIE = "/api/auth"


def _poner_cookie(response: Response, token: str, settings: Settings) -> None:
    """Cookie HttpOnly: el refresh nunca queda accesible para JavaScript."""
    response.set_cookie(
        key=NOMBRE_COOKIE,
        value=token,
        max_age=settings.jwt_refresh_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=RUTA_COOKIE,
    )


def _borrar_cookie(response: Response) -> None:
    response.delete_cookie(key=NOMBRE_COOKIE, path=RUTA_COOKIE)


async def _slug_de(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    tenant = await session.get(Tenant, tenant_id)
    return tenant.slug if tenant is not None else ""


def _identidad(usuario: Usuario, slug: str) -> IdentidadRead:
    return IdentidadRead(
        id=usuario.id,
        tenant_id=usuario.tenant_id,
        tenant_slug=slug,
        email=usuario.email,
        nombre=usuario.nombre,
        roles=[usuario.rol],
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    datos: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
    redis: Annotated[ClienteRedis, Depends(deps.cliente_redis)],
) -> TokenResponse:
    """Login del staff: rate limit primero, credenciales después."""
    ip = request.client.host if request.client else "desconocida"
    await verificar_limite_login(
        redis,
        ip=ip,
        email=datos.email,
        limite=settings.login_rate_limit,
        ventana_segundos=settings.login_rate_window_s,
    )
    usuario = await autenticar(
        session, email=datos.email, password=datos.password, tenant_slug=datos.tenant_slug
    )
    sesion = await abrir_sesion(session, settings, usuario)
    slug = await _slug_de(session, usuario.tenant_id)
    await session.commit()
    _poner_cookie(response, sesion.refresh_token, settings)
    return TokenResponse(
        access_token=sesion.access_token,
        expira_en_segundos=settings.jwt_access_min * 60,
        usuario=_identidad(usuario, slug),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
) -> TokenResponse:
    """Rota el refresh de la cookie y emite un access nuevo."""
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        raise NoAutenticado()
    sesion = await rotar_refresh(session, settings, refresh_token=token)
    slug = await _slug_de(session, sesion.usuario.tenant_id)
    await session.commit()
    _poner_cookie(response, sesion.refresh_token, settings)
    return TokenResponse(
        access_token=sesion.access_token,
        expira_en_segundos=settings.jwt_access_min * 60,
        usuario=_identidad(sesion.usuario, slug),
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Response:
    """Revoca el refresh de la cookie y la borra; idempotente."""
    token = request.cookies.get(NOMBRE_COOKIE)
    if token:
        await cerrar_sesion(session, refresh_token=token)
        await session.commit()
    _borrar_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=IdentidadRead)
async def me(
    actor: Annotated[ActorAutenticado, Depends(actor_actual)],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> IdentidadRead:
    """Identidad del usuario autenticado (sin hash ni datos clínicos)."""
    slug = await _slug_de(session, actor.tenant_id)
    return IdentidadRead(
        id=actor.usuario_id,
        tenant_id=actor.tenant_id,
        tenant_slug=slug,
        email=actor.email,
        nombre=actor.nombre,
        roles=list(actor.roles),
    )
