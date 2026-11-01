"""Migración 007: tablas plantilla y mensaje + seed 5 plantillas (tarea 1.1).

Verifica:
1. Esquema desplegado: tablas plantilla y mensaje con columnas e índices.
2. Check y unique constraints en plantilla y mensaje (idempotency_key único por tenant).
3. Función pura generar_idempotency_key_mensaje determinística (RN-CO-02).
4. Seed idempotente de las 5 plantillas base en ejecutar_seed.
5. Encadenamiento de migración 007_comunicaciones_mensajeria con 006_lista_espera.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.mensaje import (
    CanalMensaje,
    EstadoMensaje,
    Mensaje,
    generar_idempotency_key_mensaje,
)
from app.domain.plantilla import CodigoPlantilla, Plantilla
from app.domain.tenant import Tenant
from app.infrastructure.seed import ejecutar_seed


def test_generar_idempotency_key_mensaje_es_deterministica() -> None:
    """RN-CO-02: un (entidad, plantilla, ventana) genera una única clave determinística."""
    turno_id = uuid.uuid4()
    k1 = generar_idempotency_key_mensaje(
        entidad_id=turno_id,
        codigo_plantilla=CodigoPlantilla.RECORDATORIO_24H.value,
        ventana="24h",
    )
    k2 = generar_idempotency_key_mensaje(
        entidad_id=turno_id,
        codigo_plantilla=CodigoPlantilla.RECORDATORIO_24H.value,
        ventana="24h",
    )
    k3 = generar_idempotency_key_mensaje(
        entidad_id=turno_id,
        codigo_plantilla=CodigoPlantilla.CONFIRMACION_RESERVA.value,
        ventana="alta",
    )
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("msg:")


async def test_esquema_tablas_plantilla_y_mensaje(session: AsyncSession) -> None:
    """Verifica columnas e índices de plantilla y mensaje."""
    conn = await session.connection()

    def _inspeccionar(sync_conn: Any) -> tuple[set[str], set[str], set[str]]:
        insp = inspect(sync_conn)
        cols_p = {c["name"] for c in insp.get_columns("plantilla")}
        cols_m = {c["name"] for c in insp.get_columns("mensaje")}
        idxs_m = {i["name"] for i in insp.get_indexes("mensaje")}
        return cols_p, cols_m, idxs_m

    cols_p, cols_m, idxs_m = await conn.run_sync(_inspeccionar)
    assert {
        "id",
        "tenant_id",
        "codigo",
        "canal",
        "version",
        "asunto",
        "cuerpo",
        "activa",
        "created_at",
        "updated_at",
    }.issubset(cols_p)
    assert {
        "id",
        "tenant_id",
        "paciente_id",
        "turno_id",
        "lista_espera_id",
        "canal",
        "plantilla",
        "plantilla_version",
        "destino",
        "cuerpo_renderizado",
        "payload",
        "estado",
        "idempotency_key",
        "intentos",
        "max_intentos",
        "programado_para",
        "enviado_at",
        "error",
        "proveedor_message_id",
        "created_at",
        "updated_at",
    }.issubset(cols_m)
    assert "ix_mensaje_tenant_estado_programado" in idxs_m


async def test_constraints_plantilla_y_mensaje_idempotency_key(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Verifica unicidad de versión en plantilla y de idempotency_key en mensaje."""
    tenant_id = tenant_a.id
    ahora = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)

    # 1. Plantilla duplicada en (tenant_id, codigo, canal, version) -> IntegrityError
    p1 = Plantilla(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        codigo=CodigoPlantilla.RECORDATORIO_24H.value,
        canal=CanalMensaje.WA.value,
        version=1,
        cuerpo="Hola {{paciente_nombre}}",
        activa=True,
    )
    p2 = Plantilla(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        codigo=CodigoPlantilla.RECORDATORIO_24H.value,
        canal=CanalMensaje.WA.value,
        version=1,
        cuerpo="Otro texto",
        activa=True,
    )
    session.add_all([p1, p2])
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # Reinsertar tenant si rollback lo afectó o usar nuevo mensaje
    t_nuevo = Tenant(
        id=tenant_id,
        slug="tenant-msg-test",
        nombre="Tenant Msg Test",
        politicas={},
        activo=True,
    )
    session.add(t_nuevo)
    await session.flush()

    # 2. Mensaje con idempotency_key duplicada en el mismo tenant -> IntegrityError
    m1 = Mensaje(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        canal=CanalMensaje.WA.value,
        plantilla=CodigoPlantilla.RECORDATORIO_24H.value,
        plantilla_version=1,
        destino="+5491155550000",
        cuerpo_renderizado="Recordatorio 1",
        payload={},
        estado=EstadoMensaje.PENDIENTE.value,
        idempotency_key="msg:unico:24h",
        programado_para=ahora,
    )
    m2 = Mensaje(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        canal=CanalMensaje.WA.value,
        plantilla=CodigoPlantilla.RECORDATORIO_24H.value,
        plantilla_version=1,
        destino="+5491155550000",
        cuerpo_renderizado="Recordatorio 2",
        payload={},
        estado=EstadoMensaje.PENDIENTE.value,
        idempotency_key="msg:unico:24h",
        programado_para=ahora,
    )
    session.add_all([m1, m2])
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_seed_crea_5_plantillas_base_de_forma_idempotente(
    session: AsyncSession,
) -> None:
    """Verifica que ejecutar_seed cree las 5 plantillas base sin duplicar al re-ejecutar."""
    from sqlalchemy import func, select

    await ejecutar_seed(session)
    n1 = (await session.execute(select(func.count()).select_from(Plantilla))).scalar_one()
    await ejecutar_seed(session)
    n2 = (await session.execute(select(func.count()).select_from(Plantilla))).scalar_one()
    assert n1 >= 5
    assert n2 == n1


def test_migracion_007_comunicaciones_encadenada() -> None:
    """Verifica archivo 007_comunicaciones_mensajeria.py y registro en alembic/env.py."""
    ruta_mig = Path("src/backend/alembic/versions/007_comunicaciones_mensajeria.py")
    assert ruta_mig.exists()
    contenido = ruta_mig.read_text(encoding="utf-8")
    assert 'revision: str = "007_comunicaciones_mensajeria"' in contenido
    assert 'down_revision: str | None = "006_lista_espera"' in contenido
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE plantilla, mensaje TO turnos_app" in (
        contenido
    )
    assert "REVOKE ALL PRIVILEGES ON TABLE plantilla, mensaje FROM turnos_app" in contenido

    ruta_env = Path("src/backend/alembic/env.py")
    contenido_env = ruta_env.read_text(encoding="utf-8")
    assert "Plantilla" in contenido_env
    assert "Mensaje" in contenido_env
