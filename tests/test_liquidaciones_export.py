"""Exportación CSV/JSON de liquidaciones armada en servidor (C-13, tarea 4.2, D7).

Verifica:
1. CSV UTF-8 con BOM, separador `,`, decimal `.`, quoting RFC 4180 y `Content-Disposition`.
2. El CSV de una liquidación `con_debitos` incluye `debito_motivo` y una fila por turno.
3. El JSON trae cabecera + detalle con `Decimal` serializado como string.
4. R9: ni DNI, ni teléfono, ni nombre del paciente en el archivo.
5. R8: el contenido sale de la DB y no de parámetros de monto del cliente.
6. `formato` inválido -> `422` y Odontólogo -> `403` (D8).
"""

import csv
import io
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import unquote

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

COLUMNAS_CSV = [
    "periodo",
    "obra_social",
    "estado",
    "estado_arancel",
    "turno_id",
    "fecha_turno",
    "prestacion",
    "monto_reclamado",
    "monto_reconocido",
    "debito_motivo",
    "saldo_debito",
]

DNI_PACIENTE = "30999888"
TELEFONO_PACIENTE = "+5491144445555"
NOMBRE_PACIENTE = "Paciente Liquidación Export"
MOTIVO_DEBITO = "Arancel fuera de nomenclador"
PRESTACION_CON_COMILLAS = 'Consulta, control "especial"'


class _Consultorio:
    """Contexto de exportación: prestación normal, prestación con coma/comillas y 3 turnos."""

    def __init__(self) -> None:
        self.odontologo: Usuario
        self.paciente: Paciente
        self.sillon: Sillon
        self.prestacion: Prestacion
        self.prestacion_especial: Prestacion


async def _seed_consultorio(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> _Consultorio:
    """Siembra dos prestaciones con convenio OSDE y un paciente con PHI identificable."""
    ctx = _Consultorio()
    ctx.odontologo = await crear_usuario(
        tenant=tenant,
        rol=RolUsuario.ODONTOLOGO,
        email="odonto-export-seed@consultorio.test",
        nombre="Dra. Exportaciones",
    )
    ctx.paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=NOMBRE_PACIENTE,
        dni=DNI_PACIENTE,
        telefono=TELEFONO_PACIENTE,
        optin_wa=True,
        activo=True,
    )
    ctx.sillon = Sillon(
        id=uuid.uuid4(), tenant_id=tenant.id, nombre="Box Exportaciones", activo=True
    )
    ctx.prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Consulta OSDE export",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    ctx.prestacion_especial = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=PRESTACION_CON_COMILLAS,
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    # R11: los padres se insertan y confirman antes que los hijos (Postgres aplica las FK).
    session.add_all([ctx.paciente, ctx.sillon, ctx.prestacion, ctx.prestacion_especial])
    await session.flush()
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
                prestacion_id=ctx.prestacion_especial.id,
                arancel=Decimal("30000.00"),
                copago=Decimal("0.00"),
                vigencia_desde=date(2020, 1, 1),
                vigencia_hasta=None,
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
) -> Turno:
    """Crea un turno finalizado (liquidable) del consultorio."""
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=ctx.paciente.id,
        profesional_id=ctx.odontologo.id,
        sillon_id=ctx.sillon.id,
        prestacion_id=(prestacion or ctx.prestacion).id,
        inicio=inicio,
        fin=inicio + timedelta(minutes=30),
        estado=EstadoTurno.FINALIZADO.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    session.add(turno)
    await session.flush()
    return turno


async def _liquidacion_con_debitos(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> tuple[str, list[str], dict[str, str]]:
    """Arma por API una liquidación `con_debitos` de tres turnos y devuelve id, turnos y headers."""
    recepcion = await crear_usuario(
        tenant=tenant,
        email="recepcion-export-liquidacion@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    headers = autorizacion(token_para(recepcion))
    ctx = await _seed_consultorio(session, tenant, crear_usuario)
    t1 = await _turno(session, tenant, ctx, inicio=datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    t2 = await _turno(
        session,
        tenant,
        ctx,
        inicio=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        prestacion=ctx.prestacion_especial,
    )
    t3 = await _turno(
        session,
        tenant,
        ctx,
        inicio=datetime(2026, 11, 11, 9, 0, tzinfo=UTC),
        prestacion=ctx.prestacion_especial,
    )

    alta = await api.post(URL, headers=headers, json={"obra_social": "OSDE", "periodo": "202611"})
    assert alta.status_code == 201, alta.text
    liquidacion_id = alta.json()["id"]

    cierre = await api.post(f"{URL}/{liquidacion_id}/cerrar", headers=headers, json={})
    assert cierre.status_code == 200, cierre.text

    resultado = await api.post(
        f"{URL}/{liquidacion_id}/resultado",
        headers=headers,
        json={
            "resultado": "con_debitos",
            "detalles": [
                {
                    "turno_id": str(t1.id),
                    "monto_reconocido": "25000.00",
                    "debito_motivo": MOTIVO_DEBITO,
                },
                {"turno_id": str(t2.id), "monto_reconocido": "30000.00"},
                {"turno_id": str(t3.id), "monto_reconocido": "30000.00"},
            ],
        },
    )
    assert resultado.status_code == 200, resultado.text
    assert resultado.json()["estado"] == "con_debitos"
    return liquidacion_id, [str(t1.id), str(t2.id), str(t3.id)], headers


def _filas_csv(contenido: bytes) -> list[list[str]]:
    """Parsea el CSV quitando el BOM y exigiendo CRLF como separador de registros (RFC 4180)."""
    assert contenido.startswith(b"\xef\xbb\xbf"), "el CSV tiene que arrancar con BOM UTF-8"
    texto = contenido.decode("utf-8-sig")
    assert "\r\n" in texto
    return list(csv.reader(io.StringIO(texto, newline="")))


def _cabecera_descarga(respuesta: httpx.Response) -> tuple[str, str]:
    """Devuelve el `filename` ASCII y el `filename*` percent-encoded (RFC 5987)."""
    cabecera = respuesta.headers["content-disposition"]
    plano = re.search(r'filename="([^"]*)"', cabecera)
    extendido = re.search(r"filename\*=UTF-8''([^;]*)", cabecera)
    assert plano is not None, cabecera
    assert extendido is not None, cabecera
    return plano.group(1), extendido.group(1)


async def test_csv_con_debitos_incluye_motivo_y_no_expone_phi(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-OS-03 / R9: CSV con BOM, tres filas, decimal `.` y sin datos del paciente."""
    liquidacion_id, turnos, headers = await _liquidacion_con_debitos(
        api, session, tenant_a, crear_usuario, token_para, autorizacion
    )

    respuesta = await api.get(f"{URL}/{liquidacion_id}/exportar", headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith("text/csv")
    nombre, extendido = _cabecera_descarga(respuesta)
    assert nombre == "liquidacion-OSDE-202611.csv"
    assert extendido == "liquidacion-OSDE-202611.csv"

    filas = _filas_csv(respuesta.content)
    assert filas[0] == COLUMNAS_CSV
    assert len(filas) == 4, "una fila de cabecera + una por turno"

    cuerpo = {fila[4]: fila for fila in filas[1:]}
    assert set(cuerpo) == set(turnos)
    recortada = cuerpo[turnos[0]]
    assert recortada[2] == "con_debitos"
    assert recortada[3] == "vigente"
    assert recortada[5] == "2026-11-09"
    assert recortada[7] == "30000.00"
    assert recortada[8] == "25000.00"
    assert recortada[9] == MOTIVO_DEBITO
    # El saldo pendiente de la liquidación viaja en cada fila (D4/D10).
    assert recortada[10] == "5000.00"
    # Las filas sin recorte llevan el reconocido completo y el motivo vacío.
    assert cuerpo[turnos[1]][8] == "30000.00"
    assert cuerpo[turnos[1]][9] == ""
    assert cuerpo[turnos[1]][10] == "5000.00"

    # RFC 4180: la prestación con coma y comillas va entrecomillada y con comillas duplicadas.
    assert '"Consulta, control ""especial"""' in respuesta.content.decode("utf-8-sig")

    texto = respuesta.content.decode("utf-8-sig")
    assert DNI_PACIENTE not in texto
    assert TELEFONO_PACIENTE not in texto
    assert NOMBRE_PACIENTE not in texto


async def test_csv_de_borrador_deja_los_montos_reconocidos_vacios(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """Un borrador sin resultado exporta `monto_reconocido` y `debito_motivo` vacíos."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-export-borrador@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    headers = autorizacion(token_para(recepcion))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    alta = await api.post(URL, headers=headers, json={"obra_social": "OSDE", "periodo": "202611"})
    assert alta.status_code == 201, alta.text

    respuesta = await api.get(f"{URL}/{alta.json()['id']}/exportar", headers=headers)

    filas = _filas_csv(respuesta.content)
    assert filas[0] == COLUMNAS_CSV
    assert filas[1][2] == "borrador"
    assert filas[1][8] == ""
    assert filas[1][9] == ""
    # Sin resultado de la OS no hay saldo pendiente que mostrar.
    assert filas[1][10] == ""


async def test_csv_marca_el_estado_de_arancel_vencido_por_fila(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D7 / D2: la columna `estado_arancel` refleja el snapshot congelado del detalle."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-export-vencido@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    headers = autorizacion(token_para(recepcion))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    vencida = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Consulta con arancel vencido",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add(vencida)
    await session.flush()
    session.add(
        CoberturaOS(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            obra_social="OSDE",
            prestacion_id=vencida.id,
            arancel=Decimal("30000.00"),
            copago=Decimal("0.00"),
            vigencia_desde=date(2020, 1, 1),
            vigencia_hasta=date(2026, 10, 31),
            activa=True,
        )
    )
    await session.flush()
    await _turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    await _turno(
        session,
        tenant_a,
        ctx,
        inicio=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        prestacion=vencida,
    )
    alta = await api.post(URL, headers=headers, json={"obra_social": "OSDE", "periodo": "202611"})
    assert alta.status_code == 201, alta.text

    respuesta = await api.get(f"{URL}/{alta.json()['id']}/exportar", headers=headers)

    filas = _filas_csv(respuesta.content)
    estados = sorted(fila[3] for fila in filas[1:])
    assert estados == ["vencido", "vigente"]


async def test_nombre_de_archivo_normaliza_la_obra_social(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R9: el nombre del archivo no arrastra espacios ni comillas de la OS."""
    dueno = await crear_usuario(
        tenant=tenant_a,
        email="dueno-export-nombre@consultorio.test",
        rol=RolUsuario.DUENO,
    )
    headers = autorizacion(token_para(dueno))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    session.add(
        CoberturaOS(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            obra_social="SWISS MEDICAL",
            prestacion_id=ctx.prestacion.id,
            arancel=Decimal("20000.00"),
            copago=Decimal("0.00"),
            vigencia_desde=date(2020, 1, 1),
            vigencia_hasta=None,
            activa=True,
        )
    )
    await session.flush()
    await _turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    alta = await api.post(
        URL, headers=headers, json={"obra_social": "SWISS MEDICAL", "periodo": "202611"}
    )
    assert alta.status_code == 201, alta.text

    respuesta = await api.get(f"{URL}/{alta.json()['id']}/exportar", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    nombre, extendido = _cabecera_descarga(respuesta)
    assert nombre == "liquidacion-SWISS-MEDICAL-202611.csv"
    assert extendido == "liquidacion-SWISS-MEDICAL-202611.csv"


async def test_el_nombre_de_archivo_es_ascii_y_lleva_filename_rfc_5987(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """N3: el `filename` es ASCII y el nombre legible viaja percent-encoded (RFC 5987).

    Sin esto, una obra social con acentos rompe el header `latin-1` y la descarga da 500.
    """
    dueno = await crear_usuario(
        tenant=tenant_a,
        email="dueno-export-nombre-acentos@consultorio.test",
        rol=RolUsuario.DUENO,
    )
    headers = autorizacion(token_para(dueno))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    session.add(
        CoberturaOS(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            obra_social="Médico Integral",
            prestacion_id=ctx.prestacion.id,
            arancel=Decimal("20000.00"),
            copago=Decimal("0.00"),
            vigencia_desde=date(2020, 1, 1),
            vigencia_hasta=None,
            activa=True,
        )
    )
    await session.flush()
    await _turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    alta = await api.post(
        URL, headers=headers, json={"obra_social": "Médico Integral", "periodo": "202611"}
    )
    assert alta.status_code == 201, alta.text

    respuesta = await api.get(f"{URL}/{alta.json()['id']}/exportar", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cabecera = respuesta.headers["content-disposition"]
    nombre, extendido = _cabecera_descarga(respuesta)
    assert nombre.isascii(), "el `filename` tiene que ser ASCII"
    assert nombre == "liquidacion-M-dico-Integral-202611.csv"
    assert extendido == "liquidacion-M%C3%A9dico-Integral-202611.csv"
    assert unquote(extendido) == "liquidacion-Médico-Integral-202611.csv"
    # El header completo es ASCII: no rompe la codificación latin-1 del cliente HTTP.
    assert cabecera.isascii()
    assert cabecera.startswith("attachment; ")


async def test_json_incluye_cabecera_y_las_tres_filas_con_decimales_como_string(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D7: JSON con cabecera + detalle; `Decimal` serializado como string (R8)."""
    liquidacion_id, turnos, headers = await _liquidacion_con_debitos(
        api, session, tenant_a, crear_usuario, token_para, autorizacion
    )

    respuesta = await api.get(
        f"{URL}/{liquidacion_id}/exportar", headers=headers, params={"formato": "json"}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith("application/json")
    nombre, extendido = _cabecera_descarga(respuesta)
    assert nombre == "liquidacion-OSDE-202611.json"
    assert extendido == "liquidacion-OSDE-202611.json"
    cuerpo = respuesta.json()
    assert cuerpo["obra_social"] == "OSDE"
    assert cuerpo["periodo"] == "202611"
    assert cuerpo["estado"] == "con_debitos"
    assert cuerpo["total"] == "90000.00"
    assert cuerpo["total_reconocido"] == "85000.00"
    assert cuerpo["saldo_debito"] == "5000.00"
    assert [fila["turno_id"] for fila in cuerpo["detalles"]] == turnos
    assert {fila["monto_reclamado"] for fila in cuerpo["detalles"]} == {"30000.00"}
    assert cuerpo["detalles"][0]["monto_reconocido"] == "25000.00"
    assert cuerpo["detalles"][0]["debito_motivo"] == MOTIVO_DEBITO

    texto = respuesta.text
    assert DNI_PACIENTE not in texto
    assert TELEFONO_PACIENTE not in texto
    assert NOMBRE_PACIENTE not in texto


@pytest.mark.parametrize("formato", ["xml", "pdf", "CSVX"])
async def test_formato_no_soportado_responde_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    formato: str,
) -> None:
    """El contrato sólo admite `csv` y `json`: cualquier otro formato es 422 sin archivo."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-export-formato@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    headers = autorizacion(token_para(recepcion))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    await _turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    alta = await api.post(URL, headers=headers, json={"obra_social": "OSDE", "periodo": "202611"})

    respuesta = await api.get(
        f"{URL}/{alta.json()['id']}/exportar", headers=headers, params={"formato": formato}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert "content-disposition" not in respuesta.headers


async def test_odontologo_no_puede_exportar(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D8: la exportación es de Dueño/Recepción aunque el Odontólogo pueda leer."""
    liquidacion_id, _, _ = await _liquidacion_con_debitos(
        api, session, tenant_a, crear_usuario, token_para, autorizacion
    )
    odontologo = await crear_usuario(
        tenant=tenant_a,
        email="odonto-export-liquidacion@consultorio.test",
        rol=RolUsuario.ODONTOLOGO,
    )

    respuesta = await api.get(
        f"{URL}/{liquidacion_id}/exportar",
        headers=autorizacion(token_para(odontologo)),
        params={"formato": "json"},
    )

    assert respuesta.status_code == 403, respuesta.text
    assert "content-disposition" not in respuesta.headers


async def test_el_contenido_no_depende_de_montos_enviados_por_el_cliente(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R8: inyectar montos por query no cambia ni un byte de la exportación."""
    liquidacion_id, _, headers = await _liquidacion_con_debitos(
        api, session, tenant_a, crear_usuario, token_para, autorizacion
    )

    limpia = await api.get(f"{URL}/{liquidacion_id}/exportar", headers=headers)
    con_montos = await api.get(
        f"{URL}/{liquidacion_id}/exportar",
        headers=headers,
        params={
            "monto_reclamado": "1.00",
            "monto_reconocido": "999999.00",
            "total": "1.00",
            "debito_motivo": "inyectado",
        },
    )

    assert limpia.status_code == 200, limpia.text
    assert con_montos.status_code == 200, con_montos.text
    assert con_montos.content == limpia.content
    filas = _filas_csv(limpia.content)
    assert len(filas) == 4
    assert {fila[7] for fila in filas[1:]} == {"30000.00"}
    assert "999999.00" not in limpia.content.decode("utf-8-sig")
    assert "inyectado" not in limpia.content.decode("utf-8-sig")


async def test_el_csv_de_una_pagada_con_debitos_incluye_el_saldo_debito(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D4/D10: una `pagada` puede arrastrar débito; el CSV expone el saldo pendiente."""
    recepcion = await crear_usuario(
        tenant=tenant_a,
        email="recepcion-export-pagada-debitos@consultorio.test",
        rol=RolUsuario.RECEPCION,
    )
    headers = autorizacion(token_para(recepcion))
    ctx = await _seed_consultorio(session, tenant_a, crear_usuario)
    turno = await _turno(session, tenant_a, ctx, inicio=datetime(2026, 11, 9, 9, 0, tzinfo=UTC))

    alta = await api.post(URL, headers=headers, json={"obra_social": "OSDE", "periodo": "202611"})
    assert alta.status_code == 201, alta.text
    liquidacion_id = alta.json()["id"]
    cierre = await api.post(f"{URL}/{liquidacion_id}/cerrar", headers=headers, json={})
    assert cierre.status_code == 200, cierre.text

    con_debitos = await api.post(
        f"{URL}/{liquidacion_id}/resultado",
        headers=headers,
        json={
            "resultado": "con_debitos",
            "detalles": [
                {
                    "turno_id": str(turno.id),
                    "monto_reconocido": "15000.00",
                    "debito_motivo": MOTIVO_DEBITO,
                }
            ],
        },
    )
    assert con_debitos.status_code == 200, con_debitos.text
    pagada = await api.post(
        f"{URL}/{liquidacion_id}/resultado",
        headers=headers,
        json={
            "resultado": "pagada",
            "detalles": [{"turno_id": str(turno.id), "monto_reconocido": "15000.00"}],
        },
    )
    assert pagada.status_code == 200, pagada.text
    assert pagada.json()["estado"] == "pagada"

    respuesta = await api.get(f"{URL}/{liquidacion_id}/exportar", headers=headers)

    filas = _filas_csv(respuesta.content)
    assert filas[0] == COLUMNAS_CSV
    assert filas[1][2] == "pagada"
    assert filas[1][8] == "15000.00"
    assert filas[1][9] == MOTIVO_DEBITO
    assert filas[1][10] == "15000.00"
