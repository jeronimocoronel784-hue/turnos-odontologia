"""005: tablas turno y bloqueo + GRANTs.

- Reversible: `downgrade` revoca permisos y elimina bloqueo y turno en orden.
- Rol app (`APP_DB_ROLE`, default `turnos_app`): CRUD en ambas tablas.
- En dialectos no-Postgres (SQLite local) el DDL de roles se saltea solo.
"""

import os

import sqlalchemy as sa

from alembic import op

revision: str = "005_agenda_turnos"
down_revision: str | None = "004_pacientes_ficha_clinica"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ROL_APP = os.getenv("APP_DB_ROLE", "turnos_app")


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "turno",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "paciente_id",
            sa.CHAR(32),
            sa.ForeignKey("paciente.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profesional_id",
            sa.CHAR(32),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sillon_id",
            sa.CHAR(32),
            sa.ForeignKey("sillon.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "prestacion_id",
            sa.CHAR(32),
            sa.ForeignKey("prestacion.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(24), nullable=False, server_default="pendiente"),
        sa.Column("origen", sa.String(24), nullable=False, server_default="presencial"),
        sa.Column("sobreturno", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column(
            "turno_origen_id",
            sa.CHAR(32),
            sa.ForeignKey("turno.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sena_cobrada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fin > inicio", name="ck_turno_rango_valido"),
        sa.CheckConstraint(
            "(NOT sobreturno) OR (observaciones IS NOT NULL AND length(trim(observaciones)) > 0)",
            name="ck_turno_sobreturno_motivo",
        ),
    )
    op.create_index(
        "ix_turno_tenant_profesional_inicio",
        "turno",
        ["tenant_id", "profesional_id", "inicio"],
    )
    op.create_index(
        "ix_turno_tenant_sillon_inicio",
        "turno",
        ["tenant_id", "sillon_id", "inicio"],
    )
    op.create_index(
        "ix_turno_tenant_estado_inicio",
        "turno",
        ["tenant_id", "estado", "inicio"],
    )

    op.create_table(
        "bloqueo",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "profesional_id",
            sa.CHAR(32),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "sillon_id",
            sa.CHAR(32),
            sa.ForeignKey("sillon.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("motivo", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.CHAR(32),
            sa.ForeignKey("usuario.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("hasta > desde", name="ck_bloqueo_rango_valido"),
        sa.CheckConstraint(
            "profesional_id IS NOT NULL OR sillon_id IS NOT NULL",
            name="ck_bloqueo_objetivo_no_nulo",
        ),
    )
    op.create_index(
        "ix_bloqueo_tenant_desde_hasta",
        "bloqueo",
        ["tenant_id", "desde", "hasta"],
    )

    if _es_postgres():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON turno TO {ROL_APP}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON bloqueo TO {ROL_APP}")


def downgrade() -> None:
    if _es_postgres():
        op.execute(f"REVOKE ALL ON bloqueo FROM {ROL_APP}")
        op.execute(f"REVOKE ALL ON turno FROM {ROL_APP}")

    op.drop_index("ix_bloqueo_tenant_desde_hasta", table_name="bloqueo")
    op.drop_table("bloqueo")

    op.drop_index("ix_turno_tenant_estado_inicio", table_name="turno")
    op.drop_index("ix_turno_tenant_sillon_inicio", table_name="turno")
    op.drop_index("ix_turno_tenant_profesional_inicio", table_name="turno")
    op.drop_table("turno")
