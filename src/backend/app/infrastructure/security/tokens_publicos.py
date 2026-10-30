"""Tokens públicos de gestión: generación, hash y validación (C-03, D7 / RN-SE-03)."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.token_gestion import TokenGestion
from app.shared.exceptions import NoAutenticado

LARGO_TOKEN_BYTES = 32


def generar_token() -> str:
    """Token opaco de ~256 bits de entropía: no adivinable por fuerza bruta."""
    return secrets.token_urlsafe(LARGO_TOKEN_BYTES)


def hashear_token(token: str) -> str:
    """SHA-256 hex: en la DB nunca queda el token en claro."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def coincide(token: str, hash_guardado: str) -> bool:
    """Comparación en tiempo constante contra el hash persistido."""
    return hmac.compare_digest(hashear_token(token), hash_guardado)


async def crear_token_gestion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    recurso: str,
    recurso_id: str,
    vence_at: datetime,
) -> str:
    """Crea el token y devuelve el valor en claro (única vez que existe fuera de la DB)."""
    token = generar_token()
    session.add(
        TokenGestion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            recurso=recurso,
            recurso_id=recurso_id,
            token_hash=hashear_token(token),
            vence_at=vence_at,
        )
    )
    await session.flush()
    return token


async def validar_token_gestion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    token: str,
    recurso: str,
    recurso_id: str,
) -> TokenGestion:
    """Devuelve la fila si el token sirve para ese tenant y recurso; si no, 401.

    El `tenant_id` es obligatorio: el token está atado a un consultorio y un token
    de otro tenant no puede habilitar el recurso aunque el `recurso_id` coincida
    (RN-SE-03). Se filtra en la query para usar `ix_token_gestion_tenant_recurso`.
    """
    fila = (
        await session.execute(
            select(TokenGestion).where(
                TokenGestion.tenant_id == tenant_id,
                TokenGestion.token_hash == hashear_token(token),
            )
        )
    ).scalar_one_or_none()
    ahora = datetime.now(UTC)
    if fila is None or not fila.sirve_para(recurso, recurso_id, ahora):
        raise NoAutenticado("Che, ese link no es válido o ya venció. Pedí uno nuevo.")
    return fila


async def marcar_usado(session: AsyncSession, fila: TokenGestion) -> None:
    """Deja constancia del primer uso (el token sigue sirviendo hasta vencer)."""
    if fila.usado_at is None:
        fila.usado_at = datetime.now(UTC)
        await session.flush()
