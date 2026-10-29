"""002: sesiones (refresh_token) + tokens públicos (token_gestion) + GRANTs.

- Reversible: `downgrade` revoca los permisos y elimina ambas tablas (las sesiones
  activas se pierden: aceptable en v1, ver design D2/Migration Plan).
- Rol app (`APP_DB_ROLE`, default `turnos_app`): CRUD en ambas tablas. No son
  append-only: el refresh se revoca y rota, y el token público se marca usado.
- En dialectos no-Postgres (SQLite local) el DDL de roles se saltea.
"""

import os

import sqlalchemy as sa

from alembic import op

revision: str = "002_sesiones_tokens"
down_revision: str | None = "001_inicial"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ROL_APP = os.getenv("APP_DB_ROLE", "turnos_app")


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "usuario_id",
            sa.CHAR(32),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("familia_id", sa.CHAR(32), nullable=False),
        sa.Column("vence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reemplazado_por_id", sa.CHAR(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_token_tenant_usuario", "refresh_token", ["tenant_id", "usuario_id"])
    op.create_index("ix_refresh_token_familia", "refresh_token", ["familia_id"])

    op.create_table(
        "token_gestion",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column(
            "tenant_id", sa.CHAR(32), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("recurso", sa.String(40), nullable=False),
        sa.Column("recurso_id", sa.String(60), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("vence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_token_gestion_tenant_recurso",
        "token_gestion",
        ["tenant_id", "recurso", "recurso_id"],
    )

    if _es_postgres():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON refresh_token TO {ROL_APP}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON token_gestion TO {ROL_APP}")


def downgrade() -> None:
    if _es_postgres():
        op.execute(f"REVOKE ALL ON token_gestion FROM {ROL_APP}")
        op.execute(f"REVOKE ALL ON refresh_token FROM {ROL_APP}")
    op.drop_index("ix_token_gestion_tenant_recurso", table_name="token_gestion")
    op.drop_table("token_gestion")
    op.drop_index("ix_refresh_token_familia", table_name="refresh_token")
    op.drop_index("ix_refresh_token_tenant_usuario", table_name="refresh_token")
    op.drop_table("refresh_token")
