"""011_mercadopago_webhooks: tabla cobro_mp (C-12).

Revision ID: 011_mercadopago_webhooks
Revises: 010_caja_senas
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op
from app.domain.mixins import GUID

revision: str = "011_mercadopago_webhooks"
down_revision: str | None = "010_caja_senas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"

    payload_col = JSONB() if es_pg else sa.JSON()

    op.create_table(
        "cobro_mp",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sena_id",
            GUID(),
            sa.ForeignKey("sena.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mp_payment_id", sa.String(64), nullable=False),
        sa.Column("mp_preference_id", sa.String(128), nullable=True),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("estado_mp", sa.String(24), nullable=False),
        sa.Column(
            "estado_conciliacion",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'pendiente'"),
        ),
        sa.Column("payload", payload_col, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("mp_payment_id", name="uq_cobro_mp_payment_id"),
        sa.CheckConstraint(
            "estado_mp IN ('approved', 'pending', 'rejected', 'refunded', 'cancelled')",
            name="ck_cobro_mp_estado_mp_valido",
        ),
        sa.CheckConstraint(
            "estado_conciliacion IN ('pendiente', 'conciliado', 'discrepancia')",
            name="ck_cobro_mp_estado_conciliacion_valido",
        ),
        sa.CheckConstraint("monto > 0", name="ck_cobro_mp_monto_positivo"),
    )

    op.create_index("ix_cobro_mp_payment_id", "cobro_mp", ["mp_payment_id"])
    op.create_index(
        "ix_cobro_mp_tenant_conciliacion",
        "cobro_mp",
        ["tenant_id", "estado_conciliacion"],
    )

    if es_pg:
        op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE cobro_mp TO turnos_app")


def downgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"

    if es_pg:
        op.execute("REVOKE ALL PRIVILEGES ON TABLE cobro_mp FROM turnos_app")

    op.drop_index("ix_cobro_mp_tenant_conciliacion", table_name="cobro_mp")
    op.drop_index("ix_cobro_mp_payment_id", table_name="cobro_mp")
    op.drop_table("cobro_mp")
