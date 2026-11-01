"""009_presupuestos_planes: tablas presupuesto, presupuesto_item y presupuesto_turno (C-10).

Revision ID: 009_presupuestos_planes
Revises: 008_historia_clinica_odontograma
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.domain.mixins import GUID

revision: str = "009_presupuestos_planes"
down_revision: str | None = "008_historia_clinica_odontograma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "presupuesto",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "paciente_id",
            GUID(),
            sa.ForeignKey("paciente.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("obra_social", sa.String(160), nullable=True),
        sa.Column(
            "estado",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'borrador'"),
        ),
        sa.Column(
            "total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "total_cobertura_os",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "total_a_cargo",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column("validez_hasta", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('borrador', 'presentado', 'aceptado', "
            "'rechazado', 'en_curso', 'finalizado')",
            name="ck_presupuesto_estado_valido",
        ),
        sa.CheckConstraint(
            "total >= 0 AND total_cobertura_os >= 0 AND total_a_cargo >= 0",
            name="ck_presupuesto_totales_no_negativos",
        ),
    )
    op.create_index("ix_presupuesto_tenant_id", "presupuesto", ["tenant_id"])
    op.create_index(
        "ix_presupuesto_tenant_paciente_estado",
        "presupuesto",
        ["tenant_id", "paciente_id", "estado"],
    )

    op.create_table(
        "presupuesto_item",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "presupuesto_id",
            GUID(),
            sa.ForeignKey("presupuesto.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "prestacion_id",
            GUID(),
            sa.ForeignKey("prestacion.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("pieza_fdi", sa.Integer(), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("precio_unit", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "cobertura_os",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column("a_cargo", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("cantidad >= 1", name="ck_presupuesto_item_cantidad_positiva"),
        sa.CheckConstraint(
            "precio_unit >= 0 AND cobertura_os >= 0 AND a_cargo >= 0",
            name="ck_presupuesto_item_montos_no_negativos",
        ),
    )
    op.create_index("ix_presupuesto_item_tenant_id", "presupuesto_item", ["tenant_id"])
    op.create_index(
        "ix_presupuesto_item_presupuesto_id",
        "presupuesto_item",
        ["presupuesto_id"],
    )

    op.create_table(
        "presupuesto_turno",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "presupuesto_id",
            GUID(),
            sa.ForeignKey("presupuesto.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "presupuesto_item_id",
            GUID(),
            sa.ForeignKey("presupuesto_item.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "presupuesto_id",
            "turno_id",
            name="uq_presupuesto_turno_presupuesto_turno",
        ),
    )
    op.create_index("ix_presupuesto_turno_tenant_id", "presupuesto_turno", ["tenant_id"])
    op.create_index(
        "ix_presupuesto_turno_presupuesto_id",
        "presupuesto_turno",
        ["presupuesto_id"],
    )
    op.create_index("ix_presupuesto_turno_turno_id", "presupuesto_turno", ["turno_id"])

    if es_pg:
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "presupuesto, presupuesto_item, presupuesto_turno TO turnos_app"
        )


def downgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"
    if es_pg:
        op.execute(
            "REVOKE ALL PRIVILEGES ON TABLE "
            "presupuesto, presupuesto_item, presupuesto_turno FROM turnos_app"
        )

    op.drop_index("ix_presupuesto_turno_turno_id", table_name="presupuesto_turno")
    op.drop_index("ix_presupuesto_turno_presupuesto_id", table_name="presupuesto_turno")
    op.drop_index("ix_presupuesto_turno_tenant_id", table_name="presupuesto_turno")
    op.drop_table("presupuesto_turno")

    op.drop_index("ix_presupuesto_item_presupuesto_id", table_name="presupuesto_item")
    op.drop_index("ix_presupuesto_item_tenant_id", table_name="presupuesto_item")
    op.drop_table("presupuesto_item")

    op.drop_index("ix_presupuesto_tenant_paciente_estado", table_name="presupuesto")
    op.drop_index("ix_presupuesto_tenant_id", table_name="presupuesto")
    op.drop_table("presupuesto")
