"""Tests de API / E2E para Presupuestos y Planes de Tratamiento (tarea 3.1).

Verifica:
1. Creación de presupuesto con cálculo de cobertura OS vigente y agregado de items (RN-OS-01, R8).
2. Ciclo completo por API: presentar -> aceptar (bloqueado sin consentimiento si hay invasiva,
   permitido tras firmar) -> vincular turno -> finalizar (RN-CL-04, US-022).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cobertura_os import CoberturaOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def test_presupuestos_api_calculo_os_e_items(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-OS-01, R8: POST /api/presupuestos calcula cobertura OS y POST /items recalcula."""
    odontologo = await crear_usuario(
        tenant=tenant_a,
        rol=RolUsuario.ODONTOLOGO,
        email="odonto-api-c10@consultorio.test",
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Laura Presupuesto API",
        dni="38999000",
        telefono="+5491144440000",
        optin_wa=True,
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Arreglo Resina Compuesta",
        duracion_min=45,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    hoy = datetime.now(UTC).date()
    cobertura = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        obra_social="OSDE",
        prestacion_id=prestacion.id,
        arancel=Decimal("35000.00"),
        copago=Decimal("15000.00"),
        vigencia_desde=date(hoy.year - 1, 1, 1),
        vigencia_hasta=date(hoy.year + 1, 12, 31),
        activa=True,
    )
    # Sin `relationship()` el unit-of-work no ordena los INSERTs: la prestación
    # (padre) se flushEA antes que la cobertura_os (hijo) para no violar la FK.
    session.add_all([paciente, prestacion])
    await session.flush()
    session.add(cobertura)
    await session.flush()

    headers = autorizacion(token_para(odontologo))

    r_create = await api.post(
        "/api/presupuestos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "obra_social": "OSDE",
            "items": [{"prestacion_id": str(prestacion.id), "pieza_fdi": 14, "cantidad": 1}],
        },
    )
    assert r_create.status_code == 201
    body = r_create.json()
    pres_id = body["id"]
    assert Decimal(body["total"]) == Decimal("50000.00")
    assert Decimal(body["total_cobertura_os"]) == Decimal("35000.00")
    assert Decimal(body["total_a_cargo"]) == Decimal("15000.00")

    r_add = await api.post(
        f"/api/presupuestos/{pres_id}/items",
        headers=headers,
        json={"prestacion_id": str(prestacion.id), "pieza_fdi": 15, "cantidad": 1},
    )
    assert r_add.status_code == 201
    assert Decimal(r_add.json()["total_a_cargo"]) == Decimal("30000.00")

    r_list = await api.get(
        f"/api/presupuestos?paciente_id={paciente.id}",
        headers=headers,
    )
    assert r_list.status_code == 200
    assert len(r_list.json()) == 1


async def test_presupuestos_api_aceptacion_invasiva_y_vinculo_turnos(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-CL-04, US-022: presentar -> aceptar (bloqueo sin firma) -> vincular turno -> finalizar."""
    odontologo = await crear_usuario(
        tenant=tenant_a,
        rol=RolUsuario.ODONTOLOGO,
        email="odonto-inv-c10@consultorio.test",
    )
    recepcion = await crear_usuario(
        tenant=tenant_a,
        rol=RolUsuario.RECEPCION,
        email="recep-inv-c10@consultorio.test",
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Federico Plan Invasivo",
        dni="39111222",
        telefono="+5491155551111",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Box Plan Invasivo",
        activo=True,
    )
    prest_inv = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Exodoncia Quirúrgica",
        duracion_min=45,
        precio_particular=Decimal("80000.00"),
        requiere_sena=False,
        invasiva=True,
        activa=True,
    )
    session.add_all([paciente, sillon, prest_inv])
    await session.flush()

    headers = autorizacion(token_para(odontologo))
    headers_recep = autorizacion(token_para(recepcion))

    r_pres = await api.post(
        "/api/presupuestos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "items": [{"prestacion_id": str(prest_inv.id), "pieza_fdi": 38, "cantidad": 1}],
        },
    )
    assert r_pres.status_code == 201
    pres_id = r_pres.json()["id"]

    r_presentar = await api.post(f"/api/presupuestos/{pres_id}/presentar", headers=headers)
    assert r_presentar.status_code == 200
    assert r_presentar.json()["estado"] == "presentado"

    # 1. Aceptar sin consentimiento -> 409
    r_aceptar_fail = await api.post(f"/api/presupuestos/{pres_id}/aceptar", headers=headers)
    assert r_aceptar_fail.status_code == 409

    # 2. Emitir y firmar consentimiento
    r_cons = await api.post(
        "/api/consentimientos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "prestacion_id": str(prest_inv.id),
            "texto_version": "v1.0-exo",
            "texto_contenido": "Autorizo exodoncia quirúrgica.",
        },
    )
    assert r_cons.status_code == 201
    cons_id = r_cons.json()["id"]

    r_firmar = await api.post(
        f"/api/consentimientos/{cons_id}/firmar",
        headers=headers,
        json={
            "firmado_por": "Federico Plan Invasivo DNI 39111222",
            "firma_datos": "firma-presencial-xyz",
            "canal": "presencial",
        },
    )
    assert r_firmar.status_code == 200

    # 3. Ahora aceptar responde 200
    r_aceptar_ok = await api.post(f"/api/presupuestos/{pres_id}/aceptar", headers=headers)
    assert r_aceptar_ok.status_code == 200
    assert r_aceptar_ok.json()["estado"] == "aceptado"

    # 4. Crear turno y vincularlo al presupuesto
    r_turno = await api.post(
        "/api/turnos",
        headers=headers_recep,
        json={
            "paciente_id": str(paciente.id),
            "profesional_id": str(odontologo.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prest_inv.id),
            "inicio": datetime(2026, 11, 30, 10, 0, tzinfo=UTC).isoformat(),
        },
    )
    assert r_turno.status_code == 201
    turno_id = r_turno.json()["id"]

    r_vinc = await api.post(
        f"/api/presupuestos/{pres_id}/turnos",
        headers=headers,
        json={"turno_id": turno_id},
    )
    assert r_vinc.status_code == 201

    r_get_pres = await api.get(f"/api/presupuestos/{pres_id}", headers=headers)
    assert r_get_pres.status_code == 200
    assert r_get_pres.json()["estado"] == "en_curso"

    r_turnos = await api.get(f"/api/presupuestos/{pres_id}/turnos", headers=headers)
    assert r_turnos.status_code == 200
    assert len(r_turnos.json()) == 1

    r_fin = await api.post(f"/api/presupuestos/{pres_id}/finalizar", headers=headers)
    assert r_fin.status_code == 200
    assert r_fin.json()["estado"] == "finalizado"
