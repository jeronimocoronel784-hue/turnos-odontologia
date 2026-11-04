"""API de liquidaciones a obras sociales (`/api/liquidaciones`, C-13, tarea 4.1).

Verifica:
1. Ciclo completo por HTTP: alta del borrador, débitos, presentación, resultado y anulación
   del siguiente borrador (RN-OS-02, US-041, R7).
2. RBAC (D8): el Odontólogo sólo lee; Dueño y Recepción operan.
3. R4: cross-tenant responde 404 sin filtrar existencia y `tenant_id` en el body se rechaza.
4. Contrato: `409` por doble borrador, `422` por período inválido y `detalles` con
   `arancel_vencido` por fila (D2).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cobertura_os import CoberturaOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario

URL = "/api/liquidaciones"


def _dec(valor: object) -> Decimal:
    """Normaliza un monto de la respuesta JSON a `Decimal` con 2 decimales."""
    return Decimal(str(valor)).quantize(Decimal("0.01"))


class _Consultorio:
    """Contexto mínimo para liquidar por API: prestación con convenio y con arancel vencido."""

    def __init__(self) -> None:
        self.odontologo: Usuario
        self.paciente: Paciente
        self.sillon: Sillon
        self.prestacion: Prestacion
        self.prestacion_vencida: Prestacion


async def _seed_consultorio(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> _Consultorio:
    """Siembra el consultorio con una prestación vigente y otra con arancel vencido."""
    ctx = _Consultorio()
    ctx.odontologo = await crear_usuario(
        tenant=tenant,
        rol=RolUsuario.ODONTOLOGO,
        email=f"odonto-liquidaciones-api-{tenant.slug}@consultorio.test",
        nombre="Dra. Liquidaciones API",
    )
    ctx.paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Paciente Liquidación {tenant.slug}",
        dni="30999888",
        telefono="+5491144445555",
        optin_wa=True,
        activo=True,
    )
    ctx.sillon = Sillon(
        id=uuid.uuid4(), tenant_id=tenant.id, nombre=f"Box Liquidaciones {tenant.slug}", activo=True
    )
    ctx.prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Consulta OSDE {tenant.slug}",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    ctx.prestacion_vencida = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Consulta con arancel vencido {tenant.slug}",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([ctx.paciente, ctx.sillon, ctx.prestacion, ctx.prestacion_vencida])
    session.add_all(
        [
            CoberturaOS(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                obra_social="OSDE",
                prestacion_id=ctx.prestacion.id,
                arancel=Decimal("30000.00"),
                copago=Decimal("0.00"),
                vigencia_desde=date(2020, 1, 1),
                vigencia_hasta=None,
                activa=True,
            ),
            CoberturaOS(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                obra_social="OSDE",
                prestacion_id=ctx.prestacion_vencida.id,
                arancel=Decimal("30000.00"),
                copago=Decimal("0.00"),
                vigencia_desde=date(2020, 1, 1),
                vigencia_hasta=date(2026, 10, 31),
                activa=True,
            ),
        ]
    )
    await session.flush()
    return ctx


async def _turno(
    session: AsyncSession,
    tenant: Tenant,
    ctx: _Consultorio,
    *,
    inicio: datetime,
    prestacion: Prestacion | None = None,
    estado: EstadoTurno = EstadoTurno.FINALIZADO,
) -> Turno:
    """Crea un turno del consultorio con el estado pedido (finalizado = liquidable)."""
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.odontologo.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=(prestacion or ctx.prestacion).id,
        inicio=inicio,
        fin=inicio + timedelta(minutes=30),
        estado=estado.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    session.add(turno)
    await session.flush()
    return turno


def _noviembre(hora: int, dia: int = 10) -> datetime:
    return datetime(2026, 11, dia, hora, 0, tzinfo=UTC)


async def _borrador_por_api(
    api: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    obra_social: str = "OSDE",
    periodo: str = "202611",
) -> dict:
    """Alta del borrador por HTTP y devuelve el cuerpo (falla si no crea)."""
    respuesta = await api.post(
        URL, headers=headers, json={"obra_social": obra_social, "periodo": periodo}
    )
    assert respuesta.status_code == 201, respuesta.text
    return dict(respuesta.json())


async def test_ciclo_completo_por_api_hasta_anular_el_siguiente_borrador(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """POST -> PATCH -> /cerrar -> /resultado sobre 202611 y DELETE del borrador de 202612."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-ciclo-liquidacion@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    headers = autorizacion(token_para(recepcion))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    for hora in (9, 11, 15):
        await _turno(session, tenant_a, ctx, inicio=_noviembre(hora))
    await _turno(session, tenant_a, ctx, inicio=datetime(2026, 12, 3, 10, 0, tzinfo=UTC))

    # 1. Alta: totales y detalle calculados en servidor (R8).
    creada = await _borrador_por_api(api, headers)
    liquidacion_id = creada["id"]
    assert creada["estado"] == "borrador"
    assert creada["obra_social"] == "OSDE"
    assert creada["periodo"] == "202611"
    assert _dec(creada["total"]) == Decimal("90000.00")
    assert creada["created_by"] == str(recepcion.id)
    assert len(creada["detalles"]) == 3
    assert {_dec(d["monto_reclamado"]) for d in creada["detalles"]} == {Decimal("30000.00")}
    assert all(d["monto_reconocido"] is None for d in creada["detalles"])

    # 2. Detalle por id: misma cabecera con sus tres filas.
    detalle = await api.get(f"{URL}/{liquidacion_id}", headers=headers)
    assert detalle.status_code == 200, detalle.text
    assert [d["turno_id"] for d in detalle.json()["detalles"]] == [
        d["turno_id"] for d in creada["detalles"]
    ]

    # 3. Débitos: un recorte con motivo; los totales se recalculan en servidor.
    filas = creada["detalles"]
    debitos = {
        "detalles": [
            {
                "turno_id": filas[0]["turno_id"],
                "monto_reconocido": "25000.00",
                "debito_motivo": "Arancel fuera de nomenclador",
            },
            {"turno_id": filas[1]["turno_id"], "monto_reconocido": "30000.00"},
            {"turno_id": filas[2]["turno_id"], "monto_reconocido": "30000.00"},
        ]
    }
    editada = await api.patch(f"{URL}/{liquidacion_id}", headers=headers, json=debitos)
    assert editada.status_code == 200, editada.text
    cuerpo = editada.json()
    assert _dec(cuerpo["total"]) == Decimal("90000.00")
    assert _dec(cuerpo["total_reconocido"]) == Decimal("85000.00")
    recortada = next(d for d in cuerpo["detalles"] if d["turno_id"] == filas[0]["turno_id"])
    assert recortada["debito_motivo"] == "Arancel fuera de nomenclador"

    # 4. Presentación: fija actor y fecha y bloquea nuevas ediciones.
    cerrada = await api.post(
        f"{URL}/{liquidacion_id}/cerrar",
        headers=headers,
        json={"observaciones": "Presentada por mail a la OS"},
    )
    assert cerrada.status_code == 200, cerrada.text
    assert cerrada.json()["estado"] == "presentada"
    assert cerrada.json()["presentada_por"] == str(recepcion.id)
    assert cerrada.json()["presentada_at"] is not None
    assert cerrada.json()["observaciones"] == "Presentada por mail a la OS"
    reeditada = await api.patch(f"{URL}/{liquidacion_id}", headers=headers, json=debitos)
    assert reeditada.status_code == 409, reeditada.text

    # 5. Resultado: la OS reconoce menos y la liquidación queda con débitos.
    resultado = await api.post(
        f"{URL}/{liquidacion_id}/resultado",
        headers=headers,
        json={**debitos, "resultado": "con_debitos"},
    )
    assert resultado.status_code == 200, resultado.text
    assert resultado.json()["estado"] == "con_debitos"
    assert _dec(resultado.json()["total_reconocido"]) == Decimal("85000.00")
    assert resultado.json()["resuelta_por"] == str(recepcion.id)

    # 6. Segundo borrador (diciembre) anulado por baja lógica, sin borrar el detalle (R7).
    segundo = await _borrador_por_api(api, headers, periodo="202612")
    anulada = await api.request(
        "DELETE",
        f"{URL}/{segundo['id']}",
        headers=headers,
        json={"motivo": "Se cargó el turno equivocado"},
    )
    assert anulada.status_code == 200, anulada.text
    cuerpo_anulada = anulada.json()
    assert cuerpo_anulada["estado"] == "anulada"
    assert cuerpo_anulada["anulada_motivo"] == "Se cargó el turno equivocado"
    assert len(cuerpo_anulada["detalles"]) == 1
    assert cuerpo_anulada["detalles"][0]["vigente"] is False

    # 7. Listado con filtros: la anulada sigue visible para auditoría.
    listado = await api.get(
        URL, headers=headers, params={"obra_social": "osde", "periodo": "202612"}
    )
    assert listado.status_code == 200, listado.text
    assert [item["id"] for item in listado.json()] == [segundo["id"]]
    anuladas = await api.get(URL, headers=headers, params={"estado": "anulada"})
    assert [item["id"] for item in anuladas.json()] == [segundo["id"]]


async def test_detalle_expone_arancel_vencido_por_fila_con_advertencia(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D2 / RN-OS-01: el snapshot del arancel vencido viaja fila por fila en la API."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-arancel-liquidacion@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=_noviembre(9))
    await _turno(session, tenant_a, ctx, inicio=_noviembre(11), prestacion=ctx.prestacion_vencida)

    creada = await _borrador_por_api(api, headers)

    por_prestacion = {d["prestacion"]: d for d in creada["detalles"]}
    assert por_prestacion[ctx.prestacion.nombre]["arancel_vencido"] is False
    assert por_prestacion[ctx.prestacion_vencida.nombre]["arancel_vencido"] is True
    assert _dec(creada["total"]) == Decimal("60000.00")
    assert any("venció" in aviso for aviso in creada["advertencias"])

    # La marca quedó congelada en el detalle persistido: se relee igual por API.
    detalle = await api.get(f"{URL}/{creada['id']}", headers=headers)
    vencidas = [d for d in detalle.json()["detalles"] if d["arancel_vencido"]]
    assert len(vencidas) == 1


async def test_liquidacion_inexistente_responde_404(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R4: un id que no existe en el tenant responde 404 y no 500 ni 403."""
    dueno = await crear_usuario(
        tenant=tenant_a,
        email="dueno-inexistente-liquidacion@consultorio.test",
        rol=RolUsuario.DUENO,
    )
    await _seed_consultorio(session, tenant_a, crear_usuario)

    respuesta = await api.get(f"{URL}/{uuid.uuid4()}", headers=autorizacion(token_para(dueno)))

    assert respuesta.status_code == 404, respuesta.text


async def test_sin_token_responde_401(api: httpx.AsyncClient) -> None:
    """R4: sin token no hay listado ni alta de liquidaciones."""
    listado = await api.get(URL)
    alta = await api.post(URL, json={"obra_social": "OSDE", "periodo": "202611"})

    assert listado.status_code == 401, listado.text
    assert alta.status_code == 401, alta.text


@pytest.mark.parametrize(
    "operacion", ["crear", "editar", "cerrar", "resultado", "anular", "exportar"]
)
async def test_odontologo_recibe_403_en_las_operaciones_de_liquidacion(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    operacion: str,
) -> None:
    """D8: el Odontólogo consulta pero no crea, edita, presenta, resuelve, anula ni exporta."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-rbac-liquidacion@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    odontologo_usuario = await crear_usuario(
        tenant=tenant_a, email="odonto-rbac-liquidacion@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    turno = await _turno(session, tenant_a, ctx, inicio=_noviembre(9))
    creada = await _borrador_por_api(api, autorizacion(token_para(recepcion)))
    headers_odonto = autorizacion(token_para(odontologo_usuario))
    ruta = f"{URL}/{creada['id']}"

    if operacion == "crear":
        respuesta = await api.post(
            URL, headers=headers_odonto, json={"obra_social": "OSDE", "periodo": "202611"}
        )
    elif operacion == "editar":
        respuesta = await api.patch(
            ruta,
            headers=headers_odonto,
            json={
                "detalles": [
                    {
                        "turno_id": str(turno.id),
                        "monto_reconocido": "1.00",
                        "debito_motivo": "x",
                    }
                ]
            },
        )
    elif operacion == "cerrar":
        respuesta = await api.post(f"{ruta}/cerrar", headers=headers_odonto, json={})
    elif operacion == "resultado":
        respuesta = await api.post(
            f"{ruta}/resultado",
            headers=headers_odonto,
            json={
                "resultado": "pagada",
                "detalles": [{"turno_id": str(turno.id), "monto_reconocido": "1.00"}],
            },
        )
    elif operacion == "anular":
        respuesta = await api.request(
            "DELETE", ruta, headers=headers_odonto, json={"motivo": "intento del odontólogo"}
        )
    else:
        respuesta = await api.get(f"{ruta}/exportar", headers=headers_odonto)

    assert respuesta.status_code == 403, respuesta.text


async def test_odontologo_puede_listar_y_ver_el_detalle(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D8: el Odontólogo conserva la lectura de liquidaciones de su consultorio."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-lectura-liquidacion@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    odontologo_usuario = await crear_usuario(
        tenant=tenant_a,
        email="odonto-lectura-liquidacion@consultorio.test",
        rol=RolUsuario.ODONTOLOGO,
    )
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=_noviembre(9))
    creada = await _borrador_por_api(api, autorizacion(token_para(recepcion)))
    headers_odonto = autorizacion(token_para(odontologo_usuario))

    listado = await api.get(URL, headers=headers_odonto)
    detalle = await api.get(f"{URL}/{creada['id']}", headers=headers_odonto)

    assert listado.status_code == 200, listado.text
    assert [item["id"] for item in listado.json()] == [creada["id"]]
    assert detalle.status_code == 200, detalle.text
    assert len(detalle.json()["detalles"]) == 1


async def test_liquidacion_de_otro_tenant_responde_404_sin_filtrar_existencia(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R4: la liquidación del consultorio B no se ve ni se opera desde A (404, nunca 403)."""
    dueno_a = await crear_usuario(
        tenant=tenant_a, email="dueno-a-liquidacion@consultorio.test", rol=RolUsuario.DUENO
    )
    recepcion_b = await crear_usuario(
        tenant=tenant_b, email="recepcion-b-liquidacion@consultorio.test", rol=RolUsuario.RECEPCION
    )
    ctx_b = await _seed_consultorio(session, tenant_b, crear_usuario)
    await _turno(session, tenant_b, ctx_b, inicio=_noviembre(9))
    ajena = await _borrador_por_api(api, autorizacion(token_para(recepcion_b)))
    headers_a = autorizacion(token_para(dueno_a))

    lectura = await api.get(f"{URL}/{ajena['id']}", headers=headers_a)
    edicion = await api.patch(
        f"{URL}/{ajena['id']}",
        headers=headers_a,
        json={
            "detalles": [
                {
                    "turno_id": ajena["detalles"][0]["turno_id"],
                    "monto_reconocido": "1.00",
                    "debito_motivo": "x",
                }
            ]
        },
    )
    anulacion = await api.request(
        "DELETE", f"{URL}/{ajena['id']}", headers=headers_a, json={"motivo": "no es mía"}
    )
    exportacion = await api.get(f"{URL}/{ajena['id']}/exportar", headers=headers_a)

    for respuesta in (lectura, edicion, anulacion, exportacion):
        assert respuesta.status_code == 404, respuesta.text
        assert str(ajena["id"]) not in respuesta.text

    # El listado del tenant A no la incluye.
    listado = await api.get(URL, headers=headers_a)
    assert listado.json() == []


async def test_doble_borrador_de_la_misma_os_y_periodo_responde_409(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D6 / RN-OS-02: un solo borrador simultáneo por OS/período."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-duplicado-liquidacion@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    headers = autorizacion(token_para(recepcion))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=_noviembre(9))
    await _borrador_por_api(api, headers)

    repetida = await api.post(
        URL, headers=headers, json={"obra_social": "osde", "periodo": "202611"}
    )

    assert repetida.status_code == 409, repetida.text
    assert "borrador" in repetida.json()["detail"]


@pytest.mark.parametrize("periodo", ["202613", "20261", "2026-11", "abc123"])
async def test_periodo_invalido_responde_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    periodo: str,
) -> None:
    """Contrato 4.1: el período tiene que ser `yyyymm` con mes válido."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email=f"recepcion-periodo-{periodo}@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=_noviembre(9))

    respuesta = await api.post(
        URL,
        headers=autorizacion(token_para(recepcion)),
        json={"obra_social": "OSDE", "periodo": periodo},
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_tenant_id_en_el_body_se_rechaza_con_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R4 / R1: el tenant sale del JWT; el body no puede pisarlo (`extra='forbid'`)."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-tenant-body@consultorio.test", rol=RolUsuario.RECEPCION
    )
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=_noviembre(9))

    respuesta = await api.post(
        URL,
        headers=autorizacion(token_para(recepcion)),
        json={"obra_social": "OSDE", "periodo": "202611", "tenant_id": str(tenant_b.id)},
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_alta_sin_turnos_finalizados_en_el_periodo_responde_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-OS-02 / D5: sin turnos finalizados con convenio no hay liquidación que crear."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-sin-turnos-liquidacion@consultorio.test", rol=RolUsuario.DUENO
    )
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=_noviembre(9), estado=EstadoTurno.PENDIENTE)

    respuesta = await api.post(
        URL,
        headers=autorizacion(token_para(dueno)),
        json={"obra_social": "OSDE", "periodo": "202611"},
    )

    assert respuesta.status_code == 422, respuesta.text
