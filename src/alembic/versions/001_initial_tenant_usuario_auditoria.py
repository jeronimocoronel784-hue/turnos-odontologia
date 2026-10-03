"""001: tenant + usuario + auditoria (tablas, índices, constraints, GRANTs D4).

- Reversible: downgrade elimina GRANTs y las 3 tablas (válido pre-datos reales).
- Rol app (`APP_DB_ROLE`, default `turnos_app`): el rol DEBE existir (lo crea el
  init de Postgres en compose/CI). Permisos: CRUD en tenant/usuario, solo
  INSERT+SELECT en auditoria (append-only estructural, RN-SE-01).
- En dialectos no-Postgres (SQLite local) el DDL de roles se saltea.
"""

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001_inicial"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ROL_APP = os.getenv("APP_DB_ROLE", "turnos_app")


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column(
            "politicas",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_slug", "tenant", ["slug"])

    op.create_table(
        "usuario",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("matricula", sa.String(60), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "email", name="uq_usuario_tenant_email"),
        sa.CheckConstraint(
            "(rol != 'odontologo') OR (matricula IS NOT NULL AND matricula != '')",
            name="ck_usuario_matricula_odontologo",
        ),
    )
    op.create_index("ix_usuario_tenant_email", "usuario", ["tenant_id", "email"])

    op.create_table(
        "auditoria",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("actor_id", sa.CHAR(32), nullable=True),
        sa.Column("accion", sa.String(60), nullable=False),
        sa.Column("entidad", sa.String(60), nullable=False),
        sa.Column("entidad_id", sa.String(60), nullable=False),
        sa.Column("antes", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column(
            "despues", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_auditoria_tenant_entidad",
        "auditoria",
        ["tenant_id", "entidad", "entidad_id", "created_at"],
    )

    if _es_postgres():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON tenant TO {ROL_APP}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON usuario TO {ROL_APP}")
        op.execute(f"GRANT SELECT, INSERT ON auditoria TO {ROL_APP}")


def downgrade() -> None:
    if _es_postgres():
        op.execute(f"REVOKE ALL ON auditoria FROM {ROL_APP}")
        op.execute(f"REVOKE ALL ON usuario FROM {ROL_APP}")
        op.execute(f"REVOKE ALL ON tenant FROM {ROL_APP}")
    op.drop_index("ix_auditoria_tenant_entidad", table_name="auditoria")
    op.drop_table("auditoria")
    op.drop_index("ix_usuario_tenant_email", table_name="usuario")
    op.drop_table("usuario")
    op.drop_index("ix_tenant_slug", table_name="tenant")
    op.drop_table("tenant")
