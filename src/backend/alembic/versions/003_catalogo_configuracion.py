"""003: catálogo y configuración (sillon, prestacion, cobertura_os) + GRANTs.

- Reversible: `downgrade` revoca permisos y elimina las tablas en orden inverso de dependencias.
- Rol app (`APP_DB_ROLE`, default `turnos_app`): CRUD en las 3 tablas.
- En dialectos no-Postgres (SQLite local) el DDL de roles se saltea.
"""

import os

import sqlalchemy as sa

from alembic import op

revision: str = "003_catalogo_configuracion"
down_revision: str | None = "002_sesiones_tokens"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ROL_APP = os.getenv("APP_DB_ROLE", "turnos_app")


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # 1. Tabla sillon
    op.create_table(
        "sillon",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("sucursal", sa.String(120), nullable=False, server_default="central"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "sucursal", "nombre", name="uq_sillon_tenant_sucursal_nombre"
        ),
    )
    op.create_index("ix_sillon_tenant_sucursal", "sillon", ["tenant_id", "sucursal"])

    # 2. Tabla prestacion
    op.create_table(
        "prestacion",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("duracion_min", sa.Integer(), nullable=False),
        sa.Column("precio_particular", sa.Numeric(12, 2), nullable=False),
        sa.Column("requiere_sena", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("monto_sena", sa.Numeric(12, 2), nullable=True),
        sa.Column("invasiva", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "nombre", name="uq_prestacion_tenant_nombre"),
        sa.CheckConstraint("duracion_min > 0", name="ck_prestacion_duracion_positiva"),
        sa.CheckConstraint("precio_particular >= 0", name="ck_prestacion_precio_no_negativo"),
        sa.CheckConstraint(
            "(NOT requiere_sena) OR (monto_sena IS NOT NULL AND monto_sena > 0)",
            name="ck_prestacion_sena_valida",
        ),
    )
    op.create_index("ix_prestacion_tenant_activa", "prestacion", ["tenant_id", "activa"])

    # 3. Tabla cobertura_os
    op.create_table(
        "cobertura_os",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("obra_social", sa.String(160), nullable=False),
        sa.Column(
            "prestacion_id",
            sa.CHAR(32),
            sa.ForeignKey("prestacion.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("arancel", sa.Numeric(12, 2), nullable=False),
        sa.Column("copago", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("vigencia_desde", sa.Date(), nullable=False),
        sa.Column("vigencia_hasta", sa.Date(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("arancel >= 0 AND copago >= 0", name="ck_cobertura_montos_no_negativos"),
        sa.CheckConstraint(
            "vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde",
            name="ck_cobertura_vigencia_ordenada",
        ),
    )
    op.create_index("ix_cobertura_os_tenant_os", "cobertura_os", ["tenant_id", "obra_social"])
    op.create_index(
        "ix_cobertura_os_tenant_prestacion", "cobertura_os", ["tenant_id", "prestacion_id"]
    )

    if _es_postgres():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON sillon TO {ROL_APP}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON prestacion TO {ROL_APP}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON cobertura_os TO {ROL_APP}")


def downgrade() -> None:
    if _es_postgres():
        op.execute(f"REVOKE ALL ON cobertura_os FROM {ROL_APP}")
        op.execute(f"REVOKE ALL ON prestacion FROM {ROL_APP}")
        op.execute(f"REVOKE ALL ON sillon FROM {ROL_APP}")

    op.drop_index("ix_cobertura_os_tenant_prestacion", table_name="cobertura_os")
    op.drop_index("ix_cobertura_os_tenant_os", table_name="cobertura_os")
    op.drop_table("cobertura_os")

    op.drop_index("ix_prestacion_tenant_activa", table_name="prestacion")
    op.drop_table("prestacion")

    op.drop_index("ix_sillon_tenant_sucursal", table_name="sillon")
    op.drop_table("sillon")
