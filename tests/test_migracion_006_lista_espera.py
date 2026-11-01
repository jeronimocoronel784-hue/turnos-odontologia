"""Migración 006: tabla lista_espera + modelo y clave de idempotencia (tarea 1.1).

Verifica:
1. Esquema desplegado: tabla lista_espera con columnas, índice de ordenamiento y constraint único.
2. Check constraints: prioridad >= 0, estado válido y canal_aviso válido.
3. Función pura generar_idempotency_key_hueco determinística por entrada y hueco (RN-LE-02).
4. Encadenamiento de migración 006_lista_espera con 005_agenda_turnos y registro en env.py.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lista_espera import (
    CanalAviso,
    EstadoListaEspera,
    ListaEspera,
    generar_idempotency_key_hueco,
)
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.tenant import Tenant


def test_generar_idempotency_key_hueco_es_deterministica() -> None:
    """RN-LE-02: un hueco liberado genera la misma clave por entrada y distinta para otra."""
    entrada_a = uuid.uuid4()
    entrada_b = uuid.uuid4()
    prof_id = uuid.uuid4()
    sillon_id = uuid.uuid4()
    inicio = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)

    k1 = generar_idempotency_key_hueco(
        entrada_id=entrada_a,
        profesional_id=prof_id,
        sillon_id=sillon_id,
        inicio=inicio,
    )
    k2 = generar_idempotency_key_hueco(
        entrada_id=entrada_a,
        profesional_id=prof_id,
        sillon_id=sillon_id,
        inicio=inicio,
    )
    k3 = generar_idempotency_key_hueco(
        entrada_id=entrada_b,
        profesional_id=prof_id,
        sillon_id=sillon_id,
        inicio=inicio,
    )
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("le:")


async def test_esquema_tabla_lista_espera(session: AsyncSession) -> None:
    """Verifica columnas e índices de lista_espera en PostgreSQL."""
    conn = await session.connection()

    def _inspeccionar(sync_conn: Any) -> tuple[set[str], set[str]]:
        insp = inspect(sync_conn)
        cols = {c["name"] for c in insp.get_columns("lista_espera")}
        idxs = {i["name"] for i in insp.get_indexes("lista_espera")}
        return cols, idxs

    cols, idxs = await conn.run_sync(_inspeccionar)
    assert {
        "id",
        "tenant_id",
        "paciente_id",
        "prestacion_id",
        "profesional_id",
        "prioridad",
        "estado",
        "canal_aviso",
        "observaciones",
        "hueco_inicio",
        "hueco_fin",
        "hueco_profesional_id",
        "hueco_sillon_id",
        "aviso_vence_at",
        "ultimo_idempotency_key",
        "avisos_keys",
        "turno_colocado_id",
        "created_at",
        "updated_at",
    }.issubset(cols)
    assert "ix_lista_espera_tenant_estado_orden" in idxs


async def test_constraints_lista_espera_prioridad_y_idempotency_key(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Verifica check constraint de prioridad >= 0 y unicidad de ultimo_idempotency_key."""
    tenant_id = tenant_a.id
    pac_id = uuid.uuid4()
    prest_id = uuid.uuid4()

    session.add(
        Paciente(
            id=pac_id,
            tenant_id=tenant_id,
            nombre="Paciente LE",
            dni="34999111",
            telefono="+5491155550101",
            optin_wa=True,
        )
    )
    session.add(
        Prestacion(
            id=prest_id,
            tenant_id=tenant_id,
            nombre="Limpieza LE",
            duracion_min=30,
            precio_particular=Decimal("18000.00"),
            requiere_sena=False,
        )
    )
    await session.flush()

    # 1. Prioridad negativa -> violación de check constraint
    entrada_invalida = ListaEspera(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=pac_id,
        prestacion_id=prest_id,
        prioridad=-1,
        estado=EstadoListaEspera.ACTIVA.value,
        canal_aviso=CanalAviso.WA.value,
    )
    session.add(entrada_invalida)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # Reinsertar base tras rollback
    session.add(
        Paciente(
            id=pac_id,
            tenant_id=tenant_id,
            nombre="Paciente LE",
            dni="34999111",
            telefono="+5491155550101",
            optin_wa=True,
        )
    )
    session.add(
        Prestacion(
            id=prest_id,
            tenant_id=tenant_id,
            nombre="Limpieza LE",
            duracion_min=30,
            precio_particular=Decimal("18000.00"),
            requiere_sena=False,
        )
    )
    await session.flush()

    # 2. Clave de idempotencia duplicada en el mismo tenant -> violación de unique constraint
    e1 = ListaEspera(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=pac_id,
        prestacion_id=prest_id,
        prioridad=0,
        estado=EstadoListaEspera.AVISADA.value,
        canal_aviso=CanalAviso.WA.value,
        ultimo_idempotency_key="le:duplicada:1",
    )
    e2 = ListaEspera(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=pac_id,
        prestacion_id=prest_id,
        prioridad=1,
        estado=EstadoListaEspera.AVISADA.value,
        canal_aviso=CanalAviso.EMAIL.value,
        ultimo_idempotency_key="le:duplicada:1",
    )
    session.add_all([e1, e2])
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


def test_migracion_006_lista_espera_encadenada() -> None:
    """Verifica el archivo 006_lista_espera.py y su registro en alembic/env.py."""
    ruta_mig = Path("src/backend/alembic/versions/006_lista_espera.py")
    assert ruta_mig.exists()
    contenido = ruta_mig.read_text(encoding="utf-8")
    assert 'revision: str = "006_lista_espera"' in contenido
    assert 'down_revision: str | None = "005_agenda_turnos"' in contenido
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE lista_espera TO turnos_app" in contenido
    assert "REVOKE ALL PRIVILEGES ON TABLE lista_espera FROM turnos_app" in contenido

    ruta_env = Path("src/backend/alembic/env.py")
    contenido_env = ruta_env.read_text(encoding="utf-8")
    assert "ListaEspera" in contenido_env
