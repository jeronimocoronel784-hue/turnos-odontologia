"""004: tablas paciente y ficha_clinica (1:1) + GRANTs.

- Reversible: `downgrade` revoca permisos y elimina ficha_clinica y paciente en orden.
- Rol app (`APP_DB_ROLE`, default `turnos_app`): CRUD en ambas tablas.
- En dialectos no-Postgres (SQLite local) el DDL de roles se saltea solo.
"""

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004_pacientes_ficha_clinica"
down_revision: str | None = "003_catalogo_configuracion"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ROL_APP = os.getenv("APP_DB_ROLE", "turnos_app")


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # 1. Tabla paciente
    op.create_table(
        "paciente",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("dni", sa.String(20), nullable=False),
        sa.Column("telefono", sa.String(40), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("fecha_nac", sa.Date(), nullable=True),
        sa.Column("obra_social_id", sa.CHAR(32), nullable=True),
        sa.Column("nro_afiliado", sa.String(60), nullable=True),
        sa.Column("optin_wa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "dni", name="uq_paciente_tenant_dni"),
    )
    op.create_index("ix_paciente_tenant_dni", "paciente", ["tenant_id", "dni"])
    op.create_index("ix_paciente_tenant_telefono", "paciente", ["tenant_id", "telefono"])
    op.create_index("ix_paciente_tenant_activo", "paciente", ["tenant_id", "activo"])

    # 2. Tabla ficha_clinica (1:1 con paciente)
    op.create_table(
        "ficha_clinica",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "paciente_id",
            sa.CHAR(32),
            sa.ForeignKey("paciente.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("antecedentes", sa.Text(), nullable=True),
        sa.Column("alergias", sa.Text(), nullable=True),
        sa.Column("medicacion", sa.Text(), nullable=True),
        sa.Column("habitos", sa.Text(), nullable=True),
        sa.Column(
            "datos_json",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("paciente_id", name="uq_ficha_clinica_paciente_id"),
    )
    op.create_index(
        "ix_ficha_clinica_tenant_paciente", "ficha_clinica", ["tenant_id", "paciente_id"]
    )

    if _es_postgres():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON paciente TO {ROL_APP}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ficha_clinica TO {ROL_APP}")


def downgrade() -> None:
    if _es_postgres():
        op.execute(f"REVOKE ALL ON ficha_clinica FROM {ROL_APP}")
        op.execute(f"REVOKE ALL ON paciente FROM {ROL_APP}")

    op.drop_index("ix_ficha_clinica_tenant_paciente", table_name="ficha_clinica")
    op.drop_table("ficha_clinica")

    op.drop_index("ix_paciente_tenant_activo", table_name="paciente")
    op.drop_index("ix_paciente_tenant_telefono", table_name="paciente")
    op.drop_index("ix_paciente_tenant_dni", table_name="paciente")
    op.drop_table("paciente")
