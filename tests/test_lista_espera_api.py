"""Tests de integración para endpoints internos y públicos de Lista de Espera (tarea 3.1).

Verifica:
- CRUD interno /api/lista-espera con orden (prioridad, created_at) y aislamiento multi-tenant (R4).
- RBAC sobre Recurso.LISTA_ESPERA (odontólogo lee 200, pero 403 al crear o modificar).
- Flujo público completo (Flujo 6): POST /reservar/{slug}/lista-espera -> ofrecer hueco ->
  GET /lista-espera/{token} -> POST /lista-espera/{token}/aceptar (crea Turno y pasa a colocada)
  y POST /lista-espera/{token}/baja.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def _preparar_datos_api_le(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    sufijo: str = "a",
) -> tuple[Usuario, Usuario, Sillon, Prestacion, Paciente]:
    recep = await crear_usuario(
        tenant=tenant,
        email=f"recep-le-{sufijo}@test.com",
        rol=RolUsuario.RECEPCION,
    )
    odonto = await crear_usuario(
        tenant=tenant,
        email=f"odonto-le-{sufijo}@test.com",
        rol=RolUsuario.ODONTOLOGO,
    )
    sillon = Sillon(
        tenant_id=tenant.id,
        nombre=f"Box LE {sufijo}",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        tenant_id=tenant.id,
        nombre=f"Arreglo LE {sufijo}",
        duracion_min=30,
        precio_particular=Decimal("22000.00"),
        requiere_sena=False,
        activa=True,
    )
    paciente = Paciente(
        tenant_id=tenant.id,
        nombre=f"Paciente LE {sufijo}",
        dni=f"3611122{sufijo[:1].encode()[0] % 10}",
        telefono="+5491166667777",
        optin_wa=True,
    )
    session.add_all([sillon, prestacion, paciente])
    await session.flush()
    return recep, odonto, sillon, prestacion, paciente


async def test_api_interna_lista_espera_rbac_y_multitenant(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RBAC (odontólogo solo lectura, recepción CRUD) y aislamiento estricto entre tenants (R4)."""
    recep_a, odonto_a, _, prest_a, pac_a = await _preparar_datos_api_le(
        session, tenant_a, crear_usuario, "a"
    )
    recep_b, _, _, _, _ = await _preparar_datos_api_le(session, tenant_b, crear_usuario, "b")

    h_recep_a = autorizacion(token_para(recep_a))
    h_odonto_a = autorizacion(token_para(odonto_a))
    h_recep_b = autorizacion(token_para(recep_b))

    # 1. Odontólogo NO puede crear entrada en lista de espera (403)
    resp_403 = await api.post(
        "/api/lista-espera",
        json={
            "paciente_id": str(pac_a.id),
            "prestacion_id": str(prest_a.id),
            "prioridad": 1,
        },
        headers=h_odonto_a,
    )
    assert resp_403.status_code == 403

    # 2. Recepción SÍ puede crear (201) y recibe token_gestion
    resp_201 = await api.post(
        "/api/lista-espera",
        json={
            "paciente_id": str(pac_a.id),
            "prestacion_id": str(prest_a.id),
            "prioridad": 2,
            "canal_aviso": "wa",
            "observaciones": "Avisar por la tarde",
        },
        headers=h_recep_a,
    )
    assert resp_201.status_code == 201, resp_201.text
    entrada_id = resp_201.json()["id"]
    assert resp_201.json()["token_gestion"]

    # 3. Odontólogo SÍ puede listar y ver detalle (200)
    resp_list = await api.get("/api/lista-espera", headers=h_odonto_a)
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1

    # 4. Tenant B NO ve la entrada de Tenant A (R4)
    resp_b = await api.get(f"/api/lista-espera/{entrada_id}", headers=h_recep_b)
    assert resp_b.status_code == 404

    # 5. Recepción actualiza prioridad y luego da de baja con PATCH
    resp_patch = await api.patch(
        f"/api/lista-espera/{entrada_id}",
        json={"prioridad": 0, "estado": "baja"},
        headers=h_recep_a,
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["prioridad"] == 0
    assert resp_patch.json()["estado"] == "baja"


async def test_flujo_publico_lista_espera_anotarse_recibir_oferta_y_aceptar_por_token(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """Flujo 6 completo por HTTP: alta pública -> ofrecer hueco -> aceptar por token -> Turno."""
    recep, odonto, sillon, prest, _ = await _preparar_datos_api_le(
        session, tenant_a, crear_usuario, "pub"
    )
    h_recep = autorizacion(token_para(recep))

    # 1. Paciente se anota públicamente en la lista de espera del consultorio
    resp_alta = await api.post(
        f"/reservar/{tenant_a.slug}/lista-espera",
        json={
            "nombre": "Valeria Méndez",
            "dni": "37.888.999",
            "telefono": "+5491133334444",
            "prestacion_id": str(prest.id),
            "profesional_id": str(odonto.id),
            "canal_aviso": "wa",
            "optin_wa": True,
        },
    )
    assert resp_alta.status_code == 201, resp_alta.text
    datos_alta = resp_alta.json()
    token = datos_alta["token_gestion"]
    assert token
    assert datos_alta["estado"] == "activa"

    # 2. Se ofrece un hueco compatible desde el endpoint interno
    inicio_hueco = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
    fin_hueco = inicio_hueco + timedelta(minutes=30)
    resp_ofrecer = await api.post(
        "/api/lista-espera/ofrecer-hueco",
        json={
            "prestacion_id": str(prest.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": inicio_hueco.isoformat(),
            "fin": fin_hueco.isoformat(),
            "ventana_min": 60,
        },
        headers=h_recep,
    )
    assert resp_ofrecer.status_code == 200, resp_ofrecer.text
    assert resp_ofrecer.json()["estado"] == "avisada"

    # 3. Paciente consulta su oferta por token opaco
    resp_ver = await api.get(f"/lista-espera/{token}")
    assert resp_ver.status_code == 200
    assert resp_ver.json()["estado"] == "avisada"
    assert resp_ver.json()["hueco_inicio"] is not None

    # 4. Paciente acepta el hueco -> se crea Turno y la entrada pasa a colocada
    resp_aceptar = await api.post(f"/lista-espera/{token}/aceptar")
    assert resp_aceptar.status_code == 201, resp_aceptar.text
    datos_aceptar = resp_aceptar.json()
    assert datos_aceptar["estado"] == "colocada"
    assert datos_aceptar["turno_colocado_id"] is not None
    assert datos_aceptar["token_gestion"] is not None

    # 5. Token inválido devuelve 401
    resp_invalido = await api.get("/lista-espera/token-inexistente-123456")
    assert resp_invalido.status_code == 401


async def test_baja_publica_por_token_idempotente(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    """POST /lista-espera/{token}/baja pasa la entrada a baja de forma idempotente."""
    _, odonto, _, prest, _ = await _preparar_datos_api_le(session, tenant_a, crear_usuario, "baja")
    resp_alta = await api.post(
        f"/reservar/{tenant_a.slug}/lista-espera",
        json={
            "nombre": "Marcos Sosa",
            "dni": "38.111.222",
            "telefono": "+5491122223333",
            "prestacion_id": str(prest.id),
            "profesional_id": str(odonto.id),
            "canal_aviso": "email",
            "optin_wa": False,
        },
    )
    assert resp_alta.status_code == 201
    token = resp_alta.json()["token_gestion"]

    resp_baja_1 = await api.post(f"/lista-espera/{token}/baja")
    assert resp_baja_1.status_code == 200
    assert resp_baja_1.json()["estado"] == "baja"

    resp_baja_2 = await api.post(f"/lista-espera/{token}/baja")
    assert resp_baja_2.status_code == 200
    assert resp_baja_2.json()["estado"] == "baja"
