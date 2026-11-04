"""013_liquidacion_claim_unico: reclamo único por obra social y período (C-13, E.7, D12).

Revision ID: 013_liquidacion_claim_unico
Revises: 012_obras_sociales_liquidacion

Corrige las garantías de DB de la `012` (D9/D12):
- `liquidacion_detalle.reclamado BOOLEAN NOT NULL DEFAULT true`: el reclamo sigue vigente
  mientras la liquidación no esté `anulada`; el pago ya no lo libera.
- `liquidacion_os.turnos_sin_cobertura INTEGER NOT NULL DEFAULT 0`: el conteo del alta queda
  persistido en la cabecera (se relee igual que el total).
- `uq_liquidacion_detalle_turno_abierto` → `uq_liquidacion_detalle_turno_reclamado`:
  `UNIQUE (tenant_id, turno_id, lower(obra_social), periodo) WHERE reclamado`.
- `uq_liquidacion_os_borrador` se recrea con `lower(obra_social)` (la app compara la obra
  social con `lower()`, así que el índice tiene que ser case-insensitive).

El backfill de `reclamado` es portable (Python + `op.get_bind()`, sin funciones de ventana):
libera los reclamos de liquidaciones `anulada` y los duplicados preexistentes del mismo
`tenant_id`/`turno_id`/`lower(obra_social)`/`periodo`, conservando el más antiguo por
`(created_at, id)` entre las liquidaciones no anuladas, y deja el conteo en el log.

La `012` NO se modifica (ya está aplicada en bases existentes) y esta migración no crea
tablas: las columnas heredan los permisos que la `012` otorgó al rol `turnos_app`.
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013_liquidacion_claim_unico"
down_revision: str | None = "012_obras_sociales_liquidacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOGGER = logging.getLogger("alembic.runtime.migration")

ESTADO_ANULADA = "anulada"
NOMBRE_INDICE_ABIERTO = "uq_liquidacion_detalle_turno_abierto"
NOMBRE_INDICE_RECLAMADO = "uq_liquidacion_detalle_turno_reclamado"
NOMBRE_INDICE_BORRADOR = "uq_liquidacion_os_borrador"

# Lotes de UPDATE: un `IN` con miles de parámetros no escala.
TAMANO_LOTE = 500


def _backfill_reclamado() -> None:
    """Libera los reclamos que ya no están vigentes (D9/D12).

    Reglas:
    - los detalles de liquidaciones `anulada` quedan con `reclamado = false` (la anulación
      es la única baja que libera el reclamo);
    - de los reclamos duplicados del mismo turno/OS/período se conserva **el más antiguo**
      por `(created_at, id)` entre las liquidaciones no anuladas; el resto queda en `false`.
    """
    bind = op.get_bind()
    filas = (
        bind.execute(
            sa.text(
                """
            SELECT d.id AS detalle_id,
                   d.tenant_id AS tenant_id,
                   d.turno_id AS turno_id,
                   lower(d.obra_social) AS obra_social,
                   d.periodo AS periodo,
                   l.estado AS estado
            FROM liquidacion_detalle d
            JOIN liquidacion_os l ON l.id = d.liquidacion_id
            ORDER BY d.created_at ASC, d.id ASC
            """
            )
        )
        .mappings()
        .all()
    )

    # El ORDER BY de arriba ya deja el más antiguo primero: el primer reclamo vivo de cada
    # clave es el que se conserva.
    conservados: set[str] = set()
    vistas: set[tuple[str, str, str, str]] = set()
    for fila in filas:
        if fila["estado"] == ESTADO_ANULADA:
            continue
        clave = (
            fila["tenant_id"],
            fila["turno_id"],
            fila["obra_social"],
            fila["periodo"],
        )
        if clave in vistas:
            continue
        vistas.add(clave)
        conservados.add(fila["detalle_id"])

    a_liberar = [fila["detalle_id"] for fila in filas if fila["detalle_id"] not in conservados]
    if not a_liberar:
        LOGGER.info("013: backfill de `reclamado` sin filas que liberar")
        return

    sentencia = sa.text(
        "UPDATE liquidacion_detalle SET reclamado = false WHERE id IN :ids"
    ).bindparams(sa.bindparam("ids", expanding=True))
    for inicio in range(0, len(a_liberar), TAMANO_LOTE):
        bind.execute(sentencia, {"ids": a_liberar[inicio : inicio + TAMANO_LOTE]})

    LOGGER.info(
        "013: backfill de `reclamado` liberó %s de %s detalle(s)", len(a_liberar), len(filas)
    )


def upgrade() -> None:
    """Agrega el reclamo único, el conteo persistido y los índices con `lower()`."""
    op.add_column(
        "liquidacion_detalle",
        sa.Column(
            "reclamado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # El backfill va antes de crear el índice único: si no, el índice rechazaría los
    # duplicados que la propia migración tiene que liberar.
    _backfill_reclamado()
    op.add_column(
        "liquidacion_os",
        sa.Column(
            "turnos_sin_cobertura",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.drop_index(NOMBRE_INDICE_ABIERTO, table_name="liquidacion_detalle")
    op.create_index(
        NOMBRE_INDICE_RECLAMADO,
        "liquidacion_detalle",
        ["tenant_id", "turno_id", sa.text("lower(obra_social)"), "periodo"],
        unique=True,
        sqlite_where=sa.text("reclamado"),
        postgresql_where=sa.text("reclamado"),
    )

    op.drop_index(NOMBRE_INDICE_BORRADOR, table_name="liquidacion_os")
    op.create_index(
        NOMBRE_INDICE_BORRADOR,
        "liquidacion_os",
        ["tenant_id", sa.text("lower(obra_social)"), "periodo"],
        unique=True,
        sqlite_where=sa.text("estado = 'borrador'"),
        postgresql_where=sa.text("estado = 'borrador'"),
    )


def downgrade() -> None:
    """Vuelve a los índices de la `012` y dropea las dos columnas."""
    op.drop_index(NOMBRE_INDICE_RECLAMADO, table_name="liquidacion_detalle")
    op.create_index(
        NOMBRE_INDICE_ABIERTO,
        "liquidacion_detalle",
        ["tenant_id", "turno_id", "obra_social", "periodo"],
        unique=True,
        sqlite_where=sa.text("vigente"),
        postgresql_where=sa.text("vigente"),
    )

    op.drop_index(NOMBRE_INDICE_BORRADOR, table_name="liquidacion_os")
    op.create_index(
        NOMBRE_INDICE_BORRADOR,
        "liquidacion_os",
        ["tenant_id", "obra_social", "periodo"],
        unique=True,
        sqlite_where=sa.text("estado = 'borrador'"),
        postgresql_where=sa.text("estado = 'borrador'"),
    )

    op.drop_column("liquidacion_detalle", "reclamado")
    op.drop_column("liquidacion_os", "turnos_sin_cobertura")
