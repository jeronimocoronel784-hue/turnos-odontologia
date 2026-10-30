"""Tokens públicos: hash en reposo, recurso/tenant atados y vencimiento (C-03, tarea 2.3).

D7 / RN-SE-03: `secrets.token_urlsafe(32)`, SHA-256 en la DB, comparación en tiempo
constante y validación por token + recurso + recurso_id + tenant + vencimiento +
revocación. Un token de un turno no puede operar otro turno ni otro consultorio.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant import Tenant
from app.domain.token_gestion import TokenGestion
from app.infrastructure.security.tokens_publicos import (
    crear_token_gestion,
    generar_token,
    hashear_token,
    marcar_usado,
    validar_token_gestion,
)
from app.shared.exceptions import NoAutenticado


def _vence_en(**delta: int) -> datetime:
    return datetime.now(UTC) + timedelta(**delta)


async def _token(
    session: AsyncSession,
    tenant: Tenant,
    *,
    recurso: str = "turno",
    recurso_id: str = "turno-1",
    vence_at: datetime | None = None,
) -> str:
    return await crear_token_gestion(
        session,
        tenant_id=tenant.id,
        recurso=recurso,
        recurso_id=recurso_id,
        vence_at=vence_at or _vence_en(days=1),
    )


def test_los_tokens_generados_son_opacos_y_distintos() -> None:
    primero = generar_token()
    segundo = generar_token()

    assert primero != segundo
    assert len(primero) >= 43  # 32 bytes en base64url
    assert len(hashear_token(primero)) == 64


async def test_token_vigente_del_recurso_correcto_se_acepta(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    token = await _token(session, tenant_a)

    fila = await validar_token_gestion(
        session, token=token, recurso="turno", recurso_id="turno-1", tenant_id=tenant_a.id
    )

    assert fila.tenant_id == tenant_a.id
    assert fila.recurso == "turno"
    assert fila.recurso_id == "turno-1"


async def test_token_vencido_se_rechaza(session: AsyncSession, tenant_a: Tenant) -> None:
    token = await _token(session, tenant_a, vence_at=_vence_en(seconds=-1))

    with pytest.raises(NoAutenticado):
        await validar_token_gestion(
            session, token=token, recurso="turno", recurso_id="turno-1", tenant_id=tenant_a.id
        )


async def test_token_revocado_se_rechaza(session: AsyncSession, tenant_a: Tenant) -> None:
    token = await _token(session, tenant_a)
    fila = (
        await session.execute(
            select(TokenGestion).where(TokenGestion.token_hash == hashear_token(token))
        )
    ).scalar_one()
    fila.revocado_at = datetime.now(UTC)
    await session.flush()

    with pytest.raises(NoAutenticado):
        await validar_token_gestion(
            session, token=token, recurso="turno", recurso_id="turno-1", tenant_id=tenant_a.id
        )


@pytest.mark.parametrize(
    ("recurso", "recurso_id"),
    [("pago", "turno-1"), ("turno", "turno-2"), ("turno", "TURNO-1")],
)
async def test_token_de_otro_recurso_o_de_otro_id_se_rechaza(
    session: AsyncSession, tenant_a: Tenant, recurso: str, recurso_id: str
) -> None:
    token = await _token(session, tenant_a, recurso="turno", recurso_id="turno-1")

    with pytest.raises(NoAutenticado):
        await validar_token_gestion(
            session, token=token, recurso=recurso, recurso_id=recurso_id, tenant_id=tenant_a.id
        )


async def test_token_de_otro_tenant_se_rechaza(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    token = await _token(session, tenant_a)

    with pytest.raises(NoAutenticado):
        await validar_token_gestion(
            session, token=token, recurso="turno", recurso_id="turno-1", tenant_id=tenant_b.id
        )


async def test_token_inexistente_o_manipulado_se_rechaza(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    real = await _token(session, tenant_a)
    inventado = real[:-2] + ("AA" if not real.endswith("AA") else "BB")

    for candidato in (inventado, generar_token()):
        with pytest.raises(NoAutenticado):
            await validar_token_gestion(
                session,
                token=candidato,
                recurso="turno",
                recurso_id="turno-1",
                tenant_id=tenant_a.id,
            )


async def test_en_la_db_solo_queda_el_hash(session: AsyncSession, tenant_a: Tenant) -> None:
    token = await _token(session, tenant_a)
    filas = list((await session.execute(select(TokenGestion))).scalars().all())

    assert len(filas) == 1
    assert filas[0].token_hash == hashear_token(token)
    assert filas[0].token_hash != token
    assert token not in {fila.token_hash for fila in filas}
    assert len(filas[0].token_hash) == 64
    int(filas[0].token_hash, 16)  # hexadecimal válido


async def test_marcar_usado_es_idempotente_y_no_invalida_el_token(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    token = await _token(session, tenant_a)
    fila = await validar_token_gestion(
        session, token=token, recurso="turno", recurso_id="turno-1", tenant_id=tenant_a.id
    )

    await marcar_usado(session, fila)
    primer_uso = fila.usado_at
    await marcar_usado(session, fila)

    assert primer_uso is not None
    assert fila.usado_at == primer_uso
    # El link sigue sirviendo hasta vencer (design D7): no es de un solo uso.
    assert (
        await validar_token_gestion(
            session, token=token, recurso="turno", recurso_id="turno-1", tenant_id=tenant_a.id
        )
    ).id == fila.id


async def test_dos_tenants_pueden_tener_el_mismo_recurso_id(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    # El recurso_id puede coincidir entre consultorios: el tenant del token desambigua.
    token_a = await _token(session, tenant_a, recurso_id="turno-1")
    token_b = await _token(session, tenant_b, recurso_id="turno-1")

    fila_a = await validar_token_gestion(
        session, token=token_a, recurso="turno", recurso_id="turno-1", tenant_id=tenant_a.id
    )
    fila_b = await validar_token_gestion(
        session, token=token_b, recurso="turno", recurso_id="turno-1", tenant_id=tenant_b.id
    )

    assert fila_a.id != fila_b.id
    assert {fila_a.tenant_id, fila_b.tenant_id} == {tenant_a.id, tenant_b.id}
    assert uuid.UUID(str(fila_a.id)) is not None
