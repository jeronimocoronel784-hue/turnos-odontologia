"""006_lista_espera: tabla lista_espera con ordenamiento e idempotencia de avisos (C-07).

Revision ID: 006_lista_espera
Revises: 005_agenda_turnos
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.domain.mixins import GUID

revision: str = "006_lista_espera"
down_revision: str | None = "005_agenda_turnos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "lista_espera",
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
        sa.Column(
            "prestacion_id",
            GUID(),
            sa.ForeignKey("prestacion.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profesional_id",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("prioridad", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "estado",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'activa'"),
        ),
        sa.Column(
            "canal_aviso",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'wa'"),
        ),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("hueco_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hueco_fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "hueco_profesional_id",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "hueco_sillon_id",
            GUID(),
            sa.ForeignKey("sillon.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("aviso_vence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_idempotency_key", sa.String(180), nullable=True),
        sa.Column(
            "avisos_keys",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "turno_colocado_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="SET NULL"),
            nullable=True,
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
            "prioridad >= 0",
            name="ck_lista_espera_prioridad_no_negativa",
        ),
        sa.CheckConstraint(
            "estado IN ('activa', 'avisada', 'colocada', 'baja')",
            name="ck_lista_espera_estado_valido",
        ),
        sa.CheckConstraint(
            "canal_aviso IN ('wa', 'email')",
            name="ck_lista_espera_canal_valido",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "ultimo_idempotency_key",
            name="uq_lista_espera_tenant_idempotency_key",
        ),
    )
    op.create_index("ix_lista_espera_tenant_id", "lista_espera", ["tenant_id"])
    op.create_index(
        "ix_lista_espera_tenant_estado_orden",
        "lista_espera",
        ["tenant_id", "estado", "prioridad", "created_at"],
    )

    if es_pg:
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'turnos_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE lista_espera TO turnos_app;
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'turnos_app') THEN
                    REVOKE ALL PRIVILEGES ON TABLE lista_espera FROM turnos_app;
                END IF;
            END
            $$;
            """
        )

    op.drop_index("ix_lista_espera_tenant_estado_orden", table_name="lista_espera")
    op.drop_index("ix_lista_espera_tenant_id", table_name="lista_espera")
    op.drop_table("lista_espera")
