"""007_comunicaciones_mensajeria: tablas plantilla y mensaje (outbox) con idempotencia (C-08).

Revision ID: 007_comunicaciones_mensajeria
Revises: 006_lista_espera
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.domain.mixins import GUID

revision: str = "007_comunicaciones_mensajeria"
down_revision: str | None = "006_lista_espera"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "plantilla",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("codigo", sa.String(64), nullable=False),
        sa.Column("canal", sa.String(16), nullable=False, server_default=sa.text("'wa'")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("asunto", sa.String(160), nullable=True),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.CheckConstraint("version >= 1", name="ck_plantilla_version_positiva"),
        sa.CheckConstraint("canal IN ('wa', 'email')", name="ck_plantilla_canal_valido"),
        sa.UniqueConstraint(
            "tenant_id",
            "codigo",
            "canal",
            "version",
            name="uq_plantilla_tenant_codigo_canal_version",
        ),
    )
    op.create_index("ix_plantilla_tenant_id", "plantilla", ["tenant_id"])
    op.create_index(
        "ix_plantilla_tenant_codigo_activa",
        "plantilla",
        ["tenant_id", "codigo", "activa"],
    )

    op.create_table(
        "mensaje",
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
            sa.ForeignKey("paciente.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "lista_espera_id",
            GUID(),
            sa.ForeignKey("lista_espera.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("canal", sa.String(16), nullable=False, server_default=sa.text("'wa'")),
        sa.Column("plantilla", sa.String(64), nullable=False),
        sa.Column("plantilla_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("destino", sa.String(160), nullable=False),
        sa.Column("cuerpo_renderizado", sa.Text(), nullable=False),
        sa.Column("payload", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "estado",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pendiente'"),
        ),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_intentos", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("programado_para", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("proveedor_message_id", sa.String(120), nullable=True),
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
        sa.CheckConstraint("intentos >= 0", name="ck_mensaje_intentos_no_negativos"),
        sa.CheckConstraint("max_intentos >= 1", name="ck_mensaje_max_intentos_positivo"),
        sa.CheckConstraint("canal IN ('wa', 'email')", name="ck_mensaje_canal_valido"),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'enviado', 'entregado', 'leido', 'fallido', 'omitido')",
            name="ck_mensaje_estado_valido",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_mensaje_tenant_idempotency_key",
        ),
    )
    op.create_index("ix_mensaje_tenant_id", "mensaje", ["tenant_id"])
    op.create_index(
        "ix_mensaje_tenant_estado_programado",
        "mensaje",
        ["tenant_id", "estado", "programado_para"],
    )

    if es_pg:
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'turnos_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE plantilla, mensaje TO turnos_app;
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
                    REVOKE ALL PRIVILEGES ON TABLE plantilla, mensaje FROM turnos_app;
                END IF;
            END
            $$;
            """
        )

    op.drop_index("ix_mensaje_tenant_estado_programado", table_name="mensaje")
    op.drop_index("ix_mensaje_tenant_id", table_name="mensaje")
    op.drop_table("mensaje")
    op.drop_index("ix_plantilla_tenant_codigo_activa", table_name="plantilla")
    op.drop_index("ix_plantilla_tenant_id", table_name="plantilla")
    op.drop_table("plantilla")
