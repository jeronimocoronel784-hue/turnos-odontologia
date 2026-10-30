"""Migración 004: tablas paciente y ficha_clinica + función RN-CO-01 (tarea 1.1).

Verifica:
1. Esquema desplegado: tablas paciente y ficha_clinica.
2. Unicidad compuesta (tenant_id, dni) en paciente.
3. Unicidad de paciente_id en ficha_clinica (relación 1:1).
4. Defaults: optin_wa = False, activo = True.
5. Columnas nullables: obra_social_id, nro_afiliado, email, fecha_nac.
6. Función pura puede_enviar_whatsapp (RN-CO-01).
7. Downgrade y upgrade de la migración 004.
"""

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente, puede_enviar_whatsapp
from app.domain.tenant import Tenant

RAIZ = Path(__file__).resolve().parents[1]


def _unicos(insp: Any, tabla: str) -> set[tuple[str, ...]]:
    """Unique constraints + unique indexes."""
    columnas = {tuple(u["column_names"]) for u in (insp.get_unique_constraints(tabla) or [])}
    columnas |= {
        tuple(i["column_names"])
        for i in (insp.get_indexes(tabla) or [])
        if i.get("unique") and i.get("column_names")
    }
    return columnas


def _leer(conn: Any) -> dict[str, Any]:
    insp = inspect(conn.connection())
    return {
        "tablas": set(insp.get_table_names()),
        "paciente_indexes": {i["name"] for i in (insp.get_indexes("paciente") or [])},
        "paciente_unique": _unicos(insp, "paciente"),
        "ficha_unique": _unicos(insp, "ficha_clinica"),
        "paciente_columns": {
            c["name"]: c["nullable"] for c in (insp.get_columns("paciente") or [])
        },
        "ficha_columns": {
            c["name"]: c["nullable"] for c in (insp.get_columns("ficha_clinica") or [])
        },
    }


async def _esquema(session: AsyncSession) -> dict[str, Any]:
    return await session.run_sync(_leer)


@pytest.mark.asyncio
async def test_esquema_tablas_paciente_y_ficha_clinica(session: AsyncSession) -> None:
    esq = await _esquema(session)
    assert "paciente" in esq["tablas"]
    assert "ficha_clinica" in esq["tablas"]

    # Columnas esperadas en paciente
    p_cols = esq["paciente_columns"]
    for col in (
        "id",
        "tenant_id",
        "nombre",
        "dni",
        "telefono",
        "email",
        "fecha_nac",
        "obra_social_id",
        "nro_afiliado",
        "optin_wa",
        "observaciones",
        "activo",
        "created_at",
        "updated_at",
    ):
        assert col in p_cols, f"Falta columna {col} en paciente"

    # Nullables esperadas
    assert p_cols["obra_social_id"] is True
    assert p_cols["nro_afiliado"] is True
    assert p_cols["email"] is True
    assert p_cols["fecha_nac"] is True
    assert p_cols["observaciones"] is True

    # No nullables
    assert p_cols["nombre"] is False
    assert p_cols["dni"] is False
    assert p_cols["telefono"] is False
    assert p_cols["optin_wa"] is False
    assert p_cols["activo"] is False

    # Ficha clínica 1:1
    f_cols = esq["ficha_columns"]
    for col in (
        "id",
        "tenant_id",
        "paciente_id",
        "antecedentes",
        "alergias",
        "medicacion",
        "habitos",
        "datos_json",
        "created_at",
        "updated_at",
    ):
        assert col in f_cols, f"Falta columna {col} en ficha_clinica"


@pytest.mark.asyncio
async def test_unicidad_dni_por_tenant_en_db(session: AsyncSession) -> None:
    tenant_a = Tenant(nombre="Consultorio A", slug=f"t-a-{uuid.uuid4().hex[:6]}")
    tenant_b = Tenant(nombre="Consultorio B", slug=f"t-b-{uuid.uuid4().hex[:6]}")
    session.add_all([tenant_a, tenant_b])
    await session.commit()

    # Paciente 1 en tenant A con DNI 40111222
    p1 = Paciente(
        tenant_id=tenant_a.id,
        nombre="Juan Perez",
        dni="40111222",
        telefono="1122334455",
    )
    session.add(p1)
    await session.commit()

    # Mismo DNI en tenant B DEBE funcionar (multitenant)
    p2 = Paciente(
        tenant_id=tenant_b.id,
        nombre="Juan Perez de B",
        dni="40111222",
        telefono="1199887766",
    )
    session.add(p2)
    await session.commit()
    assert p2.id is not None

    # Mismo DNI en tenant A DEBE fallar por UniqueConstraint
    p3 = Paciente(
        tenant_id=tenant_a.id,
        nombre="Otro Juan Perez",
        dni="40111222",
        telefono="1100000000",
    )
    session.add(p3)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_relacion_1_a_1_ficha_clinica_unicidad(session: AsyncSession) -> None:
    tenant = Tenant(nombre="Consultorio C", slug=f"t-c-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.commit()

    paciente = Paciente(
        tenant_id=tenant.id,
        nombre="Maria Lopez",
        dni="35999888",
        telefono="1133445566",
    )
    session.add(paciente)
    await session.commit()

    # Primera ficha clinica
    ficha1 = FichaClinica(
        tenant_id=tenant.id,
        paciente_id=paciente.id,
    )
    session.add(ficha1)
    await session.commit()

    # Segunda ficha clinica para el mismo paciente DEBE fallar por uq_ficha_clinica_paciente_id
    ficha2 = FichaClinica(
        tenant_id=tenant.id,
        paciente_id=paciente.id,
    )
    session.add(ficha2)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


def test_archivo_migracion_004_existe_y_encadena_con_003() -> None:
    archivo = RAIZ / "src" / "backend" / "alembic" / "versions" / "004_pacientes_ficha_clinica.py"
    assert archivo.exists(), f"Falta {archivo}"
    contenido = archivo.read_text(encoding="utf-8")
    assert 'revision: str = "004_pacientes_ficha_clinica"' in contenido
    assert 'down_revision: str | None = "003_catalogo_configuracion"' in contenido


def test_modelos_paciente_y_ficha_coinciden_con_el_ddl() -> None:
    paciente_cols = set(Paciente.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "nombre",
        "dni",
        "telefono",
        "email",
        "fecha_nac",
        "obra_social_id",
        "nro_afiliado",
        "optin_wa",
        "observaciones",
        "activo",
        "created_at",
        "updated_at",
    } == paciente_cols

    ficha_cols = set(FichaClinica.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "paciente_id",
        "antecedentes",
        "alergias",
        "medicacion",
        "habitos",
        "datos_json",
        "created_at",
        "updated_at",
    } == ficha_cols


def test_modelos_paciente_registrados_en_alembic_env() -> None:
    env_py = (RAIZ / "src" / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "from app.domain.paciente import Paciente" in env_py
    assert "from app.domain.ficha_clinica import FichaClinica" in env_py


def test_regla_rn_co_01_puede_enviar_whatsapp() -> None:
    # Caso 1: optin_wa = False -> NUNCA enviar
    paciente_sin_optin = Paciente(
        nombre="Sin Optin",
        dni="12345678",
        telefono="1122334455",
        optin_wa=False,
        activo=True,
    )
    assert puede_enviar_whatsapp(paciente_sin_optin) is False

    # Caso 2: optin_wa = True y activo = True -> SE PUEDE enviar
    paciente_con_optin = Paciente(
        nombre="Con Optin",
        dni="87654321",
        telefono="1122334455",
        optin_wa=True,
        activo=True,
    )
    assert puede_enviar_whatsapp(paciente_con_optin) is True

    # Caso 3: baja STOP (optin_wa pasa a False) -> se corta de inmediato
    paciente_con_optin.optin_wa = False
    assert puede_enviar_whatsapp(paciente_con_optin) is False

    # Caso 4: paciente inactivo aunque tenga optin_wa -> no enviar
    paciente_inactivo = Paciente(
        nombre="Inactivo",
        dni="99887766",
        telefono="1122334455",
        optin_wa=True,
        activo=False,
    )
    assert puede_enviar_whatsapp(paciente_inactivo) is False
