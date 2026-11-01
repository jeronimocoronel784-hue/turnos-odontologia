"""Tests de API / E2E para Historia Clínica, Odontograma FDI y Consentimiento (tarea 3.1).

Verifica:
1. RBAC (RN-CL-03): RECEPCION lee (200) pero recibe 403 al editar ficha, evolución u odontograma.
2. ODONTOLOGO actualiza ficha (genera evolución), crea evolución y eventos FDI (RN-CL-01).
3. Flujo invasivo (RN-CL-02, RN-SE-03): turno invasivo bloquea 'presente' (409) sin firma
   y pasa (200) tras firmar en GET/POST /firmar/{token}.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def test_rbac_recepcion_solo_lectura_y_odontologo_edita_hc_y_odontograma(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-CL-01, RN-CL-03: recepción lee (200) pero no edita clínica (403); odontólogo edita."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        rol=RolUsuario.RECEPCION,
        email="recep-c09@consultorio.test",
    )
    odontologo = await crear_usuario(
        tenant=tenant_a,
        rol=RolUsuario.ODONTOLOGO,
        email="odonto-c09@consultorio.test",
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Sofía Clínica API",
        dni="34555666",
        telefono="+5491177778888",
        optin_wa=True,
        activo=True,
    )
    session.add(paciente)
    await session.flush()
    ficha = FichaClinica(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
    )
    session.add(ficha)
    await session.flush()

    headers_recep = autorizacion(token_para(recepcion))
    headers_odonto = autorizacion(token_para(odontologo))

    # 1. Recepción puede leer ficha y odontograma
    r_get_ficha = await api.get(f"/api/pacientes/{paciente.id}/ficha", headers=headers_recep)
    assert r_get_ficha.status_code == 200

    # 2. Recepción NO puede editar ficha, crear evolución ni registrar evento FDI -> 403
    r_put_recep = await api.put(
        f"/api/pacientes/{paciente.id}/ficha",
        headers=headers_recep,
        json={"alergias": "Ibuprofeno"},
    )
    assert r_put_recep.status_code == 403

    r_ev_recep = await api.post(
        f"/api/pacientes/{paciente.id}/evoluciones",
        headers=headers_recep,
        json={"nota": "Intento de evolución desde recepción"},
    )
    assert r_ev_recep.status_code == 403

    r_odo_recep = await api.post(
        f"/api/odontograma/{paciente.id}/eventos",
        headers=headers_recep,
        json={"pieza_fdi": 16, "superficie": "oclusal", "evento": "caries"},
    )
    assert r_odo_recep.status_code == 403

    # 3. Odontólogo actualiza ficha -> 200 y genera evolución automática
    r_put_odonto = await api.put(
        f"/api/pacientes/{paciente.id}/ficha",
        headers=headers_odonto,
        json={"alergias": "Ibuprofeno", "antecedentes": "Sin antecedentes quirúrgicos"},
    )
    assert r_put_odonto.status_code == 200
    assert r_put_odonto.json()["alergias"] == "Ibuprofeno"

    # 4. Odontólogo agrega evolución y adjunto
    r_ev_odonto = await api.post(
        f"/api/pacientes/{paciente.id}/evoluciones",
        headers=headers_odonto,
        json={"nota": "Control periodontal satisfactorio."},
    )
    assert r_ev_odonto.status_code == 201

    r_list_ev = await api.get(f"/api/pacientes/{paciente.id}/evoluciones", headers=headers_recep)
    assert r_list_ev.status_code == 200
    assert len(r_list_ev.json()) == 2

    r_adj = await api.post(
        f"/api/pacientes/{paciente.id}/adjuntos",
        headers=headers_odonto,
        json={
            "tipo": "rx",
            "nombre_archivo": "rx-16.png",
            "mime_type": "image/png",
            "tamano_bytes": 64000,
            "storage_key": f"tenants/{tenant_a.id}/rx-16.png",
            "evolucion_id": r_ev_odonto.json()["id"],
        },
    )
    assert r_adj.status_code == 201

    # 5. Odontólogo registra dos eventos en pieza 16 y consulta odontograma e historial
    r_pe1 = await api.post(
        f"/api/odontograma/{paciente.id}/eventos",
        headers=headers_odonto,
        json={"pieza_fdi": 16, "superficie": "oclusal", "evento": "caries"},
    )
    assert r_pe1.status_code == 201

    r_pe2 = await api.post(
        f"/api/odontograma/{paciente.id}/eventos",
        headers=headers_odonto,
        json={"pieza_fdi": 16, "superficie": "oclusal", "evento": "obturacion"},
    )
    assert r_pe2.status_code == 201

    r_odo = await api.get(f"/api/odontograma/{paciente.id}", headers=headers_odonto)
    assert r_odo.status_code == 200
    assert r_odo.json()["piezas"][0]["superficies"]["oclusal"] == "obturacion"

    r_hist = await api.get(
        f"/api/odontograma/{paciente.id}/piezas/16/historial",
        headers=headers_odonto,
    )
    assert r_hist.status_code == 200
    assert [e["evento"] for e in r_hist.json()] == ["caries", "obturacion"]


async def test_flujo_consentimiento_por_token_y_desbloqueo_presente_invasiva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-CL-02, RN-SE-03: bloqueo de 'presente' sin firma y habilitación tras /firmar/{token}."""
    odontologo = await crear_usuario(
        tenant=tenant_a,
        rol=RolUsuario.ODONTOLOGO,
        email="odonto-cons@consultorio.test",
    )
    recepcion = await crear_usuario(
        tenant=tenant_a,
        rol=RolUsuario.RECEPCION,
        email="recep-cons@consultorio.test",
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Diego Invasiva",
        dni="35666777",
        telefono="+5491188889999",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Box Cirugía",
        activo=True,
    )
    prestacion_inv = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Cirugía de Terceros Molares",
        duracion_min=60,
        precio_particular=Decimal("90000.00"),
        requiere_sena=False,
        invasiva=True,
        activa=True,
    )
    session.add_all([paciente, sillon, prestacion_inv])
    await session.flush()

    headers_recep = autorizacion(token_para(recepcion))

    # 1. Crear turno para prestación invasiva y pasarlo a confirmado
    r_turno = await api.post(
        "/api/turnos",
        headers=headers_recep,
        json={
            "paciente_id": str(paciente.id),
            "profesional_id": str(odontologo.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prestacion_inv.id),
            "inicio": datetime(2026, 11, 27, 15, 0, tzinfo=UTC).isoformat(),
        },
    )
    assert r_turno.status_code == 201
    turno_id = r_turno.json()["id"]

    r_conf = await api.patch(
        f"/api/turnos/{turno_id}/estado",
        headers=headers_recep,
        json={"estado": "confirmado"},
    )
    assert r_conf.status_code == 200

    # 2. Intentar marcar PRESENTE sin consentimiento firmado -> 409
    r_pres_bloqueado = await api.patch(
        f"/api/turnos/{turno_id}/estado",
        headers=headers_recep,
        json={"estado": "presente"},
    )
    assert r_pres_bloqueado.status_code == 409
    assert "consentimiento" in r_pres_bloqueado.json()["detail"].lower()

    # 3. Emitir consentimiento y firmarlo por ruta pública /firmar/{token}
    r_cons = await api.post(
        "/api/consentimientos",
        headers=headers_recep,
        json={
            "paciente_id": str(paciente.id),
            "prestacion_id": str(prestacion_inv.id),
            "turno_id": turno_id,
            "texto_version": "v1.0-cirugia-3m",
            "texto_contenido": "Autorizo cirugía de terceros molares.",
        },
    )
    assert r_cons.status_code == 201
    token_firma = r_cons.json()["token_firma"]
    assert token_firma

    r_pub_get = await api.get(f"/firmar/{token_firma}")
    assert r_pub_get.status_code == 200
    assert r_pub_get.json()["firmado"] is False

    r_pub_post = await api.post(
        f"/firmar/{token_firma}",
        json={
            "firmado_por": "Diego Invasiva DNI 35666777",
            "firma_datos": "firma-base64-trazo",
        },
    )
    assert r_pub_post.status_code == 200
    assert r_pub_post.json()["firma_hash"] is not None

    # 4. Ahora recepción pasa el turno a PRESENTE -> 200 OK
    r_pres_ok = await api.patch(
        f"/api/turnos/{turno_id}/estado",
        headers=headers_recep,
        json={"estado": "presente"},
    )
    assert r_pres_ok.status_code == 200
    assert r_pres_ok.json()["estado"] == "presente"
