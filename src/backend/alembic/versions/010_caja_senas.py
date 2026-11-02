"""010_caja_senas: tablas sena, cierre_caja y movimiento_caja (C-11).

Revision ID: 010_caja_senas
Revises: 009_presupuestos_planes
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.domain.mixins import GUID

revision: str = "010_caja_senas"
down_revision: str | None = "009_presupuestos_planes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "sena",
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
            sa.ForeignKey("turno.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "estado",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'pendiente'"),
        ),
        sa.Column("mp_payment_id", sa.String(64), nullable=True),
        sa.Column("vence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("turno_id", name="uq_sena_turno_id"),
        sa.UniqueConstraint("mp_payment_id", name="uq_sena_mp_payment_id"),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'cobrada', 'aplicada', 'devuelta', 'vencida')",
            name="ck_sena_estado_valido",
        ),
        sa.CheckConstraint("monto > 0", name="ck_sena_monto_positivo"),
    )
    op.create_index("ix_sena_tenant_estado", "sena", ["tenant_id", "estado"])

    op.create_table(
        "cierre_caja",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column(
            "total_sistema",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column("total_contado", sa.Numeric(12, 2), nullable=True),
        sa.Column("diferencia", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "estado",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'abierto'"),
        ),
        sa.Column(
            "abierto_por",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "cerrado_por",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("cerrado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reabierto_motivo", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "fecha", name="uq_cierre_caja_tenant_fecha"),
        sa.CheckConstraint(
            "estado IN ('abierto', 'cerrado')",
            name="ck_cierre_caja_estado_valido",
        ),
        sa.CheckConstraint(
            "(estado <> 'cerrado') OR (total_contado IS NOT NULL AND diferencia IS NOT NULL "
            "AND cerrado_por IS NOT NULL AND cerrado_at IS NOT NULL)",
            name="ck_cierre_caja_cierre_completo",
        ),
    )

    op.create_table(
        "movimiento_caja",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(16), nullable=False),
        sa.Column("concepto", sa.String(160), nullable=False),
        sa.Column("medio", sa.String(16), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "sena_id",
            GUID(),
            sa.ForeignKey("sena.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("cobro_mp_id", GUID(), nullable=True),
        sa.Column(
            "cierre_id",
            GUID(),
            sa.ForeignKey("cierre_caja.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("tipo IN ('ingreso', 'egreso')", name="ck_movimiento_caja_tipo_valido"),
        sa.CheckConstraint(
            "medio IN ('efectivo', 'debito', 'credito', 'transferencia', 'mp')",
            name="ck_movimiento_caja_medio_valido",
        ),
        sa.CheckConstraint("monto > 0", name="ck_movimiento_caja_monto_positivo"),
        sa.CheckConstraint(
            "length(trim(concepto)) > 0",
            name="ck_movimiento_caja_concepto_no_vacio",
        ),
    )
    op.create_index(
        "ix_movimiento_caja_tenant_created_at",
        "movimiento_caja",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_movimiento_caja_tenant_cierre_id",
        "movimiento_caja",
        ["tenant_id", "cierre_id"],
    )
    op.create_index("ix_movimiento_caja_turno_id", "movimiento_caja", ["turno_id"])

    if es_pg:
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "sena, cierre_caja, movimiento_caja TO turnos_app"
        )


def downgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"
    if es_pg:
        op.execute(
            "REVOKE ALL PRIVILEGES ON TABLE sena, cierre_caja, movimiento_caja FROM turnos_app"
        )

    op.drop_index("ix_movimiento_caja_turno_id", table_name="movimiento_caja")
    op.drop_index("ix_movimiento_caja_tenant_cierre_id", table_name="movimiento_caja")
    op.drop_index("ix_movimiento_caja_tenant_created_at", table_name="movimiento_caja")
    op.drop_table("movimiento_caja")

    op.drop_table("cierre_caja")

    op.drop_index("ix_sena_tenant_estado", table_name="sena")
    op.drop_table("sena")
