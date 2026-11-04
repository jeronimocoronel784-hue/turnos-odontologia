"""Migración 011: tabla cobro_mp para integración de Mercado Pago (tarea 1.1).

Verifica:
1. Modelo CobroMP y enums de estado (EstadoMP, EstadoConciliacionMP).
2. Esquema desplegado: columnas e índices de cobro_mp.
3. Idempotencia y constraints: mp_payment_id único, monto > 0, checks de estado.
4. Encadenamiento de la migración 011_mercadopago_webhooks y GRANT/REVOKE.
"""

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.mercadopago import CobroMP, EstadoConciliacionMP, EstadoMP
from app.domain.tenant import Tenant


def test_enums_mercadopago() -> None:
    """Verifica que los enums de MP contengan los valores esperados."""
    assert EstadoMP.APPROVED.value == "approved"
    assert EstadoMP.PENDING.value == "pending"
    assert EstadoMP.REJECTED.value == "rejected"
    assert EstadoMP.REFUNDED.value == "refunded"
    assert EstadoMP.CANCELLED.value == "cancelled"

    assert EstadoConciliacionMP.PENDIENTE.value == "pendiente"
    assert EstadoConciliacionMP.CONCILIADO.value == "conciliado"
    assert EstadoConciliacionMP.DISCREPANCIA.value == "discrepancia"


async def test_esquema_tabla_cobro_mp(session: AsyncSession) -> None:
    """Verifica columnas e índices de la tabla cobro_mp."""
    conn = await session.connection()

    def _inspeccionar(sync_conn: Any) -> dict[str, Any]:
        insp = inspect(sync_conn)
        return {
            "cols": {c["name"] for c in insp.get_columns("cobro_mp")},
            "indices": {i["name"] for i in insp.get_indexes("cobro_mp")},
        }

    info = await conn.run_sync(_inspeccionar)
    cols = info["cols"]
    indices = info["indices"]

    assert {
        "id",
        "tenant_id",
        "turno_id",
        "sena_id",
        "mp_payment_id",
        "mp_preference_id",
        "monto",
        "estado_mp",
        "estado_conciliacion",
        "payload",
        "created_at",
    }.issubset(cols)

    assert "ix_cobro_mp_payment_id" in indices
    assert "ix_cobro_mp_tenant_conciliacion" in indices


async def test_persistencia_cobro_mp_y_unicidad_payment_id(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Verifica persistencia y rechazo de mp_payment_id duplicado (RN-PA-03)."""
    payment_id = f"mp_pay_{uuid.uuid4().hex[:8]}"
    cobro1 = CobroMP(
        tenant_id=tenant_a.id,
        mp_payment_id=payment_id,
        mp_preference_id="pref_999",
        monto=Decimal("15000.00"),
        estado_mp=EstadoMP.APPROVED.value,
        estado_conciliacion=EstadoConciliacionMP.PENDIENTE.value,
        payload={"id": 12345678, "status": "approved"},
    )
    session.add(cobro1)
    await session.commit()

    # Intento de duplicar el mismo mp_payment_id
    cobro2 = CobroMP(
        tenant_id=tenant_a.id,
        mp_payment_id=payment_id,
        mp_preference_id="pref_otra",
        monto=Decimal("15000.00"),
        estado_mp=EstadoMP.APPROVED.value,
        estado_conciliacion=EstadoConciliacionMP.PENDIENTE.value,
        payload={"id": 12345678, "status": "approved"},
    )
    session.add(cobro2)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_constraints_monto_y_estados_cobro_mp(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Triangulación: monto debe ser > 0 y los estados deben ser valores válidos."""
    # Monto cero o negativo
    cobro_invalido = CobroMP(
        tenant_id=tenant_a.id,
        mp_payment_id=f"mp_pay_{uuid.uuid4().hex[:8]}",
        monto=Decimal("0.00"),
        estado_mp=EstadoMP.APPROVED.value,
        estado_conciliacion=EstadoConciliacionMP.PENDIENTE.value,
        payload={"dummy": True},
    )
    session.add(cobro_invalido)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # Estado MP inválido
    cobro_invalido_estado = CobroMP(
        tenant_id=tenant_a.id,
        mp_payment_id=f"mp_pay_{uuid.uuid4().hex[:8]}",
        monto=Decimal("5000.00"),
        estado_mp="estado_falso",
        estado_conciliacion=EstadoConciliacionMP.PENDIENTE.value,
        payload={"dummy": True},
    )
    session.add(cobro_invalido_estado)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


def test_migracion_011_encadenamiento_y_declaracion() -> None:
    """Valida sintaxis, encabezados y down_revision de 011_mercadopago_webhooks.py."""
    mig_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "backend"
        / "alembic"
        / "versions"
        / "011_mercadopago_webhooks.py"
    )
    assert mig_path.exists(), f"Falta el archivo de migración en {mig_path}"

    contenido = mig_path.read_text(encoding="utf-8")
    assert 'revision: str = "011_mercadopago_webhooks"' in contenido
    assert 'down_revision: str | None = "010_caja_senas"' in contenido
    assert "def upgrade() -> None:" in contenido
    assert "def downgrade() -> None:" in contenido
    assert "op.create_table(" in contenido
    assert '"cobro_mp"' in contenido
    assert "turnos_app" in contenido
