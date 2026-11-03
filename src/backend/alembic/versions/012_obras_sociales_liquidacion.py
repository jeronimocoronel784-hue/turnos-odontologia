"""012_obras_sociales_liquidacion: tablas liquidacion_os y liquidacion_detalle (C-13).

Revision ID: 012_obras_sociales_liquidacion
Revises: 011_mercadopago_webhooks

RN-OS-02: índices únicos parciales para impedir el mismo turno en dos liquidaciones abiertas
y un segundo `borrador` de la misma obra social/período. El rollback revoca los GRANT del rol
`turnos_app` y elimina las tablas; no toca datos ni tablas existentes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.domain.mixins import GUID

revision: str = "012_obras_sociales_liquidacion"
down_revision: str | None = "011_mercadopago_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "liquidacion_os",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("obra_social", sa.String(160), nullable=False),
        sa.Column("periodo", sa.String(6), nullable=False),
        sa.Column(
            "estado",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'borrador'"),
        ),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("total_reconocido", sa.Numeric(12, 2), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "presentada_por",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("presentada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resuelta_por",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("resuelta_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulada_motivo", sa.Text(), nullable=True),
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
            "estado IN ('borrador', 'presentada', 'pagada', 'con_debitos', 'anulada')",
            name="ck_liquidacion_os_estado_valido",
        ),
        sa.CheckConstraint("length(periodo) = 6", name="ck_liquidacion_os_periodo_largo"),
        sa.CheckConstraint(
            "total >= 0 AND (total_reconocido IS NULL OR total_reconocido >= 0) "
            "AND (total_reconocido IS NULL OR total_reconocido <= total)",
            name="ck_liquidacion_os_totales_no_negativos",
        ),
        sa.CheckConstraint(
            "estado IN ('borrador', 'anulada') "
            "OR (presentada_por IS NOT NULL AND presentada_at IS NOT NULL)",
            name="ck_liquidacion_os_presentada_completa",
        ),
        sa.CheckConstraint(
            "estado NOT IN ('pagada', 'con_debitos') "
            "OR (total_reconocido IS NOT NULL AND resuelta_por IS NOT NULL "
            "AND resuelta_at IS NOT NULL)",
            name="ck_liquidacion_os_resuelta_completa",
        ),
        sa.CheckConstraint(
            "estado <> 'anulada' "
            "OR (anulada_motivo IS NOT NULL AND length(trim(anulada_motivo)) > 0)",
            name="ck_liquidacion_os_anulada_motivo",
        ),
    )
    # D6: un solo `borrador` simultáneo por obra social y período (complementarias permitidas).
    op.create_index(
        "uq_liquidacion_os_borrador",
        "liquidacion_os",
        ["tenant_id", "obra_social", "periodo"],
        unique=True,
        sqlite_where=sa.text("estado = 'borrador'"),
        postgresql_where=sa.text("estado = 'borrador'"),
    )
    op.create_index(
        "ix_liquidacion_os_tenant_os_periodo",
        "liquidacion_os",
        ["tenant_id", "obra_social", "periodo"],
    )
    op.create_index("ix_liquidacion_os_tenant_estado", "liquidacion_os", ["tenant_id", "estado"])

    op.create_table(
        "liquidacion_detalle",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "liquidacion_id",
            GUID(),
            sa.ForeignKey("liquidacion_os.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("obra_social", sa.String(160), nullable=False),
        sa.Column("periodo", sa.String(6), nullable=False),
        sa.Column("monto_reclamado", sa.Numeric(12, 2), nullable=False),
        sa.Column("monto_reconocido", sa.Numeric(12, 2), nullable=True),
        sa.Column("debito_motivo", sa.Text(), nullable=True),
        sa.Column(
            "arancel_vencido",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint("liquidacion_id", "turno_id", name="uq_liquidacion_detalle_turno"),
        sa.CheckConstraint(
            "monto_reclamado >= 0 AND (monto_reconocido IS NULL OR "
            "(monto_reconocido >= 0 AND monto_reconocido <= monto_reclamado))",
            name="ck_liquidacion_detalle_montos",
        ),
        sa.CheckConstraint(
            "monto_reconocido IS NULL OR monto_reconocido = monto_reclamado "
            "OR (debito_motivo IS NOT NULL AND length(trim(debito_motivo)) > 0)",
            name="ck_liquidacion_detalle_debito_motivo",
        ),
        sa.CheckConstraint("length(periodo) = 6", name="ck_liquidacion_detalle_periodo_largo"),
    )
    # RN-OS-02 / D3: un turno abierto por OS/período; se libera al pagar o anular.
    op.create_index(
        "uq_liquidacion_detalle_turno_abierto",
        "liquidacion_detalle",
        ["tenant_id", "turno_id", "obra_social", "periodo"],
        unique=True,
        sqlite_where=sa.text("vigente"),
        postgresql_where=sa.text("vigente"),
    )
    op.create_index(
        "ix_liquidacion_detalle_liquidacion_id", "liquidacion_detalle", ["liquidacion_id"]
    )
    op.create_index(
        "ix_liquidacion_detalle_tenant_turno", "liquidacion_detalle", ["tenant_id", "turno_id"]
    )

    if es_pg:
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "liquidacion_os, liquidacion_detalle TO turnos_app"
        )


def downgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"
    if es_pg:
        op.execute(
            "REVOKE ALL PRIVILEGES ON TABLE "
            "liquidacion_os, liquidacion_detalle FROM turnos_app"
        )

    op.drop_index("ix_liquidacion_detalle_tenant_turno", table_name="liquidacion_detalle")
    op.drop_index("ix_liquidacion_detalle_liquidacion_id", table_name="liquidacion_detalle")
    op.drop_index("uq_liquidacion_detalle_turno_abierto", table_name="liquidacion_detalle")
    op.drop_table("liquidacion_detalle")

    op.drop_index("ix_liquidacion_os_tenant_estado", table_name="liquidacion_os")
    op.drop_index("ix_liquidacion_os_tenant_os_periodo", table_name="liquidacion_os")
    op.drop_index("uq_liquidacion_os_borrador", table_name="liquidacion_os")
    op.drop_table("liquidacion_os")
