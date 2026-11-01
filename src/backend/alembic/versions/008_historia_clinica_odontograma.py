"""008_historia_clinica_odontograma: evolucion, odontograma, pieza_evento y consentimiento (C-09).

Revision ID: 008_historia_clinica_odontograma
Revises: 007_comunicaciones_mensajeria
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.domain.mixins import GUID

revision: str = "008_historia_clinica_odontograma"
down_revision: str | None = "007_comunicaciones_mensajeria"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "evolucion",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ficha_clinica_id",
            GUID(),
            sa.ForeignKey("ficha_clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "paciente_id",
            GUID(),
            sa.ForeignKey("paciente.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "profesional_id",
            GUID(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("nota", sa.Text(), nullable=False),
        sa.Column(
            "es_correccion_de_id",
            GUID(),
            sa.ForeignKey("evolucion.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_evolucion_tenant_id", "evolucion", ["tenant_id"])
    op.create_index(
        "ix_evolucion_tenant_paciente_created",
        "evolucion",
        ["tenant_id", "paciente_id", "created_at"],
    )
    op.create_index(
        "ix_evolucion_ficha_created",
        "evolucion",
        ["ficha_clinica_id", "created_at"],
    )

    op.create_table(
        "odontograma",
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
            sa.ForeignKey("paciente.id", ondelete="CASCADE"),
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
        sa.UniqueConstraint("tenant_id", "paciente_id", name="uq_odontograma_tenant_paciente"),
    )
    op.create_index("ix_odontograma_tenant_id", "odontograma", ["tenant_id"])
    op.create_index(
        "ix_odontograma_tenant_paciente",
        "odontograma",
        ["tenant_id", "paciente_id"],
    )

    op.create_table(
        "pieza_evento",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            GUID(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "odontograma_id",
            GUID(),
            sa.ForeignKey("odontograma.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("pieza_fdi", sa.Integer(), nullable=False),
        sa.Column("superficie", sa.String(24), nullable=False),
        sa.Column("evento", sa.String(24), nullable=False),
        sa.Column(
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observacion", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "(pieza_fdi BETWEEN 11 AND 18) OR (pieza_fdi BETWEEN 21 AND 28) OR "
            "(pieza_fdi BETWEEN 31 AND 38) OR (pieza_fdi BETWEEN 41 AND 48) OR "
            "(pieza_fdi BETWEEN 51 AND 55) OR (pieza_fdi BETWEEN 61 AND 65) OR "
            "(pieza_fdi BETWEEN 71 AND 75) OR (pieza_fdi BETWEEN 81 AND 85)",
            name="ck_pieza_evento_pieza_fdi_valida",
        ),
        sa.CheckConstraint(
            "superficie IN ('oclusal', 'mesial', 'distal', "
            "'vestibular', 'lingual', 'radicular', 'total')",
            name="ck_pieza_evento_superficie_valida",
        ),
        sa.CheckConstraint(
            "evento IN ('sano', 'caries', 'obturacion', 'corona', 'endodoncia', 'implante', "
            "'extraccion', 'ausente', 'sellador', 'provisoria')",
            name="ck_pieza_evento_tipo_valido",
        ),
    )
    op.create_index("ix_pieza_evento_tenant_id", "pieza_evento", ["tenant_id"])
    op.create_index(
        "ix_pieza_evento_odontograma_pieza_created",
        "pieza_evento",
        ["odontograma_id", "pieza_fdi", "created_at"],
    )

    op.create_table(
        "adjunto_clinico",
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
            "ficha_clinica_id",
            GUID(),
            sa.ForeignKey("ficha_clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "evolucion_id",
            GUID(),
            sa.ForeignKey("evolucion.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "pieza_evento_id",
            GUID(),
            sa.ForeignKey("pieza_evento.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tipo", sa.String(16), nullable=False),
        sa.Column("nombre_archivo", sa.String(200), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
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
        sa.CheckConstraint("tipo IN ('rx', 'foto', 'pdf')", name="ck_adjunto_clinico_tipo_valido"),
        sa.CheckConstraint("tamano_bytes > 0", name="ck_adjunto_clinico_tamano_positivo"),
    )
    op.create_index("ix_adjunto_clinico_tenant_id", "adjunto_clinico", ["tenant_id"])
    op.create_index(
        "ix_adjunto_clinico_tenant_paciente",
        "adjunto_clinico",
        ["tenant_id", "paciente_id", "created_at"],
    )

    op.create_table(
        "consentimiento",
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
            "turno_id",
            GUID(),
            sa.ForeignKey("turno.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("texto_version", sa.String(64), nullable=False),
        sa.Column("texto_contenido", sa.Text(), nullable=False),
        sa.Column("firma_hash", sa.String(64), nullable=True),
        sa.Column("firmado_por", sa.String(160), nullable=True),
        sa.Column("firmado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canal", sa.String(16), nullable=False, server_default=sa.text("'presencial'")),
        sa.Column("revocado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revocado_motivo", sa.Text(), nullable=True),
        sa.Column("revocado_at", sa.DateTime(timezone=True), nullable=True),
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
            "canal IN ('presencial', 'token')",
            name="ck_consentimiento_canal_valido",
        ),
    )
    op.create_index("ix_consentimiento_tenant_id", "consentimiento", ["tenant_id"])
    op.create_index(
        "ix_consentimiento_tenant_paciente_prestacion",
        "consentimiento",
        ["tenant_id", "paciente_id", "prestacion_id"],
    )
    op.create_index("ix_consentimiento_turno_id", "consentimiento", ["turno_id"])

    if es_pg:
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "evolucion, odontograma, pieza_evento, adjunto_clinico, consentimiento TO turnos_app"
        )


def downgrade() -> None:
    bind = op.get_bind()
    es_pg = bind.dialect.name == "postgresql"
    if es_pg:
        op.execute(
            "REVOKE ALL PRIVILEGES ON TABLE "
            "evolucion, odontograma, pieza_evento, adjunto_clinico, consentimiento FROM turnos_app"
        )

    op.drop_index("ix_consentimiento_turno_id", table_name="consentimiento")
    op.drop_index(
        "ix_consentimiento_tenant_paciente_prestacion",
        table_name="consentimiento",
    )
    op.drop_index("ix_consentimiento_tenant_id", table_name="consentimiento")
    op.drop_table("consentimiento")

    op.drop_index("ix_adjunto_clinico_tenant_paciente", table_name="adjunto_clinico")
    op.drop_index("ix_adjunto_clinico_tenant_id", table_name="adjunto_clinico")
    op.drop_table("adjunto_clinico")

    op.drop_index("ix_pieza_evento_odontograma_pieza_created", table_name="pieza_evento")
    op.drop_index("ix_pieza_evento_tenant_id", table_name="pieza_evento")
    op.drop_table("pieza_evento")

    op.drop_index("ix_odontograma_tenant_paciente", table_name="odontograma")
    op.drop_index("ix_odontograma_tenant_id", table_name="odontograma")
    op.drop_table("odontograma")

    op.drop_index("ix_evolucion_ficha_created", table_name="evolucion")
    op.drop_index("ix_evolucion_tenant_paciente_created", table_name="evolucion")
    op.drop_index("ix_evolucion_tenant_id", table_name="evolucion")
    op.drop_table("evolucion")
