"""Casos de uso de sesión: login, rotación de refresh y logout (C-03, D2).

Los eventos de auth se auditan en la misma transacción; cuando el caso de uso
falla (401/429) el registro de auditoría se commitea ANTES de levantar el error
para que el intento quede registrado igual (RN-SE-01).
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auditoria import registrar_auditoria
from app.domain.refresh_token import RefreshToken
from app.domain.tenant import Tenant
from app.domain.usuario import Usuario
from app.infrastructure.security import jwt as jwt_seguridad
from app.infrastructure.security.passwords import verificar_password
from app.infrastructure.security.tokens_publicos import hashear_token
from app.shared.exceptions import CredencialesInvalidas, NoAutenticado, SolicitudInvalida
from app.shared.settings import Settings

LARGO_REFRESH_BYTES = 48


@dataclass(frozen=True)
class SesionEmitida:
    """Resultado de un login o refresh exitoso."""

    access_token: str
    refresh_token: str
    usuario: Usuario


def _roles(usuario: Usuario) -> list[str]:
    return [str(usuario.rol)]


def _nuevo_refresh() -> str:
    return secrets.token_urlsafe(LARGO_REFRESH_BYTES)


async def autenticar(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    tenant_slug: str | None = None,
) -> Usuario:
    """Valida credenciales y devuelve el usuario; cualquier falla es 401 genérico."""
    consulta = (
        select(Usuario)
        .join(Tenant, Usuario.tenant_id == Tenant.id)
        .where(
            func.lower(Usuario.email) == email.strip().lower(),
            Tenant.activo.is_(True),
        )
    )
    if tenant_slug:
        consulta = consulta.where(Tenant.slug == tenant_slug)

    candidatos = list((await session.execute(consulta)).scalars().all())
    if len(candidatos) > 1:
        raise SolicitudInvalida(
            "Ese email está en más de un consultorio. Indicá el consultorio para entrar."
        )
    if not candidatos:
        raise CredencialesInvalidas()

    usuario = candidatos[0]
    if not usuario.activo or not verificar_password(password, usuario.password_hash):
        await registrar_auditoria(
            session,
            tenant_id=usuario.tenant_id,
            actor_id=usuario.id,
            accion="auth.login_fallido",
            entidad="usuario",
            entidad_id=str(usuario.id),
        )
        await session.commit()
        raise CredencialesInvalidas()

    await registrar_auditoria(
        session,
        tenant_id=usuario.tenant_id,
        actor_id=usuario.id,
        accion="auth.login",
        entidad="usuario",
        entidad_id=str(usuario.id),
    )
    return usuario


async def abrir_sesion(
    session: AsyncSession, settings: Settings, usuario: Usuario
) -> SesionEmitida:
    """Emite el primer par access + refresh de una sesión nueva."""
    refresh = _nuevo_refresh()
    ahora = datetime.now(UTC)
    session.add(
        RefreshToken(
            id=uuid.uuid4(),
            tenant_id=usuario.tenant_id,
            usuario_id=usuario.id,
            token_hash=hashear_token(refresh),
            familia_id=uuid.uuid4(),
            vence_at=ahora + timedelta(days=settings.jwt_refresh_days),
        )
    )
    await session.flush()
    access, _ = jwt_seguridad.emitir_access(
        usuario_id=usuario.id,
        tenant_id=usuario.tenant_id,
        roles=_roles(usuario),
        email=usuario.email,
        settings=settings,
    )
    return SesionEmitida(access_token=access, refresh_token=refresh, usuario=usuario)


async def _revocar_familia(session: AsyncSession, fila: RefreshToken, ahora: datetime) -> None:
    """Mata toda la cadena de rotaciones: el refresh vigente también deja de servir."""
    hermanos = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.familia_id == fila.familia_id,
                RefreshToken.revocado_at.is_(None),
            )
        )
    ).scalars()
    for hermano in hermanos:
        hermano.revocado_at = ahora
    await registrar_auditoria(
        session,
        tenant_id=fila.tenant_id,
        actor_id=fila.usuario_id,
        accion="auth.refresh_reuso",
        entidad="refresh_token",
        entidad_id=str(fila.id),
        despues={"familia_id": str(fila.familia_id)},
    )


async def rotar_refresh(
    session: AsyncSession, settings: Settings, *, refresh_token: str
) -> SesionEmitida:
    """Rota el refresh; el reúso de uno ya rotado revoca la familia entera."""
    ahora = datetime.now(UTC)
    fila = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hashear_token(refresh_token))
        )
    ).scalar_one_or_none()
    if fila is None:
        raise NoAutenticado()

    if fila.revocado_at is not None:
        await _revocar_familia(session, fila, ahora)
        await session.commit()
        raise NoAutenticado()

    if fila.vence_at <= ahora:
        raise NoAutenticado()

    usuario = await session.get(Usuario, fila.usuario_id)
    if usuario is None or not usuario.activo or usuario.tenant_id != fila.tenant_id:
        raise NoAutenticado()

    nuevo = _nuevo_refresh()
    reemplazo = RefreshToken(
        id=uuid.uuid4(),
        tenant_id=fila.tenant_id,
        usuario_id=fila.usuario_id,
        token_hash=hashear_token(nuevo),
        familia_id=fila.familia_id,
        vence_at=ahora + timedelta(days=settings.jwt_refresh_days),
    )
    session.add(reemplazo)
    await session.flush()

    fila.revocado_at = ahora
    fila.reemplazado_por_id = reemplazo.id
    await session.flush()

    access, _ = jwt_seguridad.emitir_access(
        usuario_id=usuario.id,
        tenant_id=usuario.tenant_id,
        roles=_roles(usuario),
        email=usuario.email,
        settings=settings,
    )
    return SesionEmitida(access_token=access, refresh_token=nuevo, usuario=usuario)


async def cerrar_sesion(session: AsyncSession, *, refresh_token: str) -> None:
    """Revoca el refresh presentado; idempotente si ya estaba revocado o no existe."""
    fila = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hashear_token(refresh_token))
        )
    ).scalar_one_or_none()
    if fila is None or fila.revocado_at is not None:
        return
    fila.revocado_at = datetime.now(UTC)
    await registrar_auditoria(
        session,
        tenant_id=fila.tenant_id,
        actor_id=fila.usuario_id,
        accion="auth.logout",
        entidad="refresh_token",
        entidad_id=str(fila.id),
    )
