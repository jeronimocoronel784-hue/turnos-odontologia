"""Lectura del trail append-only vía `GET /api/auditoria` (C-14, sección 1 y 2).

Cubre:
- Filtros combinados (`entidad`, `entidad_id`, `actor_id`, `accion`, `desde`, `hasta`).
- Orden `created_at DESC, id DESC` y paginación keyset sin duplicados ni huecos.
- Keyset con `created_at` empatados (el `id` desempata, D2).
- Cursor corrupto ⇒ `422`; rango invertido y `limite` fuera de 1–200 ⇒ `422`.
- Fechas sin offset interpretadas en `America/Argentina/Buenos_Aires` (D2/D12).
- Matriz de 3 roles sobre el trail y aislamiento multi-tenant (`R4`).

Fixtures 100% sintéticas (R13); la DB es la real del test, sin mocks (R11).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
from app.domain.paciente import Paciente
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario

URL = "/api/auditoria"

ActorFactory = Callable[..., Awaitable[Usuario]]
TokenFactory = Callable[..., str]
HeaderFactory = Callable[[str], dict[str, str]]


async def _evento(
    session: AsyncSession,
    tenant: Tenant,
    *,
    accion: str = "turno.cambiar_estado",
    entidad: str = "turno",
    entidad_id: str = "turno-1",
    actor_id: uuid.UUID | None = None,
    created_at: datetime,
    antes: dict[str, object] | None = None,
    despues: dict[str, object] | None = None,
) -> Auditoria:
    """Inserta un evento del trail con `created_at` controlado (append-only, R7)."""
    evento = Auditoria(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        actor_id=actor_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        antes=antes,
        despues=despues,
        created_at=created_at,
    )
    session.add(evento)
    await session.flush()
    return evento


async def _dueno(
    crear_usuario: ActorFactory,
    tenant: Tenant,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> dict[str, str]:
    usuario = await crear_usuario(
        tenant, email="dueno-auditoria@consultorio.test", rol=RolUsuario.DUENO
    )
    return autorizacion(token_para(usuario))


# ---------------------------------------------------------------------------
# 1.1 Filtros, orden y paginación keyset
# ---------------------------------------------------------------------------


async def test_filtros_combinados_devuelven_solo_los_eventos_que_coinciden(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)
    actor_1 = uuid.uuid4()
    actor_2 = uuid.uuid4()

    e1 = await _evento(
        session, tenant_a, actor_id=actor_1, created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    )
    e2 = await _evento(
        session,
        tenant_a,
        actor_id=actor_1,
        entidad_id="turno-2",
        created_at=datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    )
    await _evento(
        session, tenant_a, actor_id=actor_2, created_at=datetime(2026, 11, 2, 11, 0, tzinfo=UTC)
    )
    await _evento(
        session,
        tenant_a,
        actor_id=actor_1,
        entidad="paciente",
        entidad_id="paciente-1",
        accion="paciente.actualizar",
        created_at=datetime(2026, 11, 2, 12, 0, tzinfo=UTC),
    )
    await _evento(
        session, tenant_a, actor_id=actor_1, created_at=datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
    )

    respuesta = await api.get(
        URL,
        headers=headers,
        params={
            "entidad": "turno",
            "actor_id": str(actor_1),
            "accion": "turno.cambiar_estado",
            "desde": "2026-11-01T00:00:00+00:00",
            "hasta": "2026-11-03T00:00:00+00:00",
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    ids = [evento["id"] for evento in respuesta.json()["eventos"]]
    assert ids == [str(e2.id), str(e1.id)], (
        "solo turno + actor_1 + rango, del más nuevo al más viejo"
    )


async def test_paginacion_keyset_sin_duplicados_ni_huecos(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)
    eventos = [
        await _evento(
            session,
            tenant_a,
            entidad_id=f"turno-{i}",
            created_at=datetime(2026, 11, 1, 8 + i, 0, tzinfo=UTC),
        )
        for i in range(5)
    ]

    recolectados: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        params: dict[str, str | int] = {"limite": 2}
        if cursor:
            params["cursor"] = cursor
        respuesta = await api.get(URL, headers=headers, params=params)
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        recolectados.extend(evento["id"] for evento in cuerpo["eventos"])
        cursor = cuerpo["siguiente_cursor"]
        if cursor is None:
            break

    esperado = [str(e.id) for e in sorted(eventos, key=lambda e: e.created_at, reverse=True)]
    # Los `created_at` son distintos: el orden es estrictamente descendente y sin repeticiones.
    assert recolectados == esperado
    assert len(set(recolectados)) == 5
    assert cursor is None


async def test_paginacion_keyset_con_created_at_empatados(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)
    mismo_momento = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
    eventos = [
        await _evento(session, tenant_a, entidad_id=f"turno-{i}", created_at=mismo_momento)
        for i in range(3)
    ]
    esperado = [str(e.id) for e in sorted(eventos, key=lambda e: e.id, reverse=True)]

    primera = await api.get(URL, headers=headers, params={"limite": 2})
    assert primera.status_code == 200, primera.text
    parte_1 = [evento["id"] for evento in primera.json()["eventos"]]
    cursor = primera.json()["siguiente_cursor"]
    assert cursor is not None

    segunda = await api.get(URL, headers=headers, params={"limite": 2, "cursor": cursor})
    assert segunda.status_code == 200, segunda.text
    parte_2 = [evento["id"] for evento in segunda.json()["eventos"]]
    assert segunda.json()["siguiente_cursor"] is None

    assert parte_1 + parte_2 == esperado
    assert len(set(parte_1 + parte_2)) == 3


async def test_cursor_corrupto_se_rechaza_con_422(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)

    respuesta = await api.get(URL, headers=headers, params={"cursor": "no-es-base64!!"})

    assert respuesta.status_code == 422, respuesta.text
    detalle = respuesta.json()["detail"]
    assert "cursor" in detalle.lower()
    assert "sin cursor" in detalle.lower()
    assert "eventos" not in respuesta.json()


async def test_fechas_sin_offset_se_interpretan_en_art(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)
    # 2026-11-01T02:30Z = 31/10 23:30 en ART; 2026-11-01T03:30Z = 01/11 00:30 en ART.
    antes_del_dia = await _evento(
        session, tenant_a, entidad_id="oct-31", created_at=datetime(2026, 11, 1, 2, 30, tzinfo=UTC)
    )
    ya_del_dia = await _evento(
        session, tenant_a, entidad_id="nov-1", created_at=datetime(2026, 11, 1, 3, 30, tzinfo=UTC)
    )

    desde = await api.get(URL, headers=headers, params={"desde": "2026-11-01T00:00:00"})
    assert desde.status_code == 200, desde.text
    assert [evento["id"] for evento in desde.json()["eventos"]] == [str(ya_del_dia.id)]

    hasta = await api.get(URL, headers=headers, params={"hasta": "2026-11-01T00:00:00"})
    assert hasta.status_code == 200, hasta.text
    assert [evento["id"] for evento in hasta.json()["eventos"]] == [str(antes_del_dia.id)]


async def test_rango_de_fechas_invertido_responde_422(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)

    respuesta = await api.get(
        URL,
        headers=headers,
        params={"desde": "2026-11-10T00:00:00+00:00", "hasta": "2026-11-01T00:00:00+00:00"},
    )

    assert respuesta.status_code == 422, respuesta.text
    assert "posterior" in respuesta.json()["detail"].lower()
    assert "eventos" not in respuesta.json()


@pytest.mark.parametrize("limite", [0, 500])
async def test_limite_fuera_de_rango_responde_422(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
    limite: int,
) -> None:
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)

    respuesta = await api.get(URL, headers=headers, params={"limite": limite})

    assert respuesta.status_code == 422, respuesta.text
    detalle = respuesta.json()["detail"]
    assert "1" in detalle and "200" in detalle
    assert "eventos" not in respuesta.json()


# ---------------------------------------------------------------------------
# 2.2 Matriz de 3 roles sobre el trail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "esperado"),
    [(RolUsuario.DUENO, 200), (RolUsuario.RECEPCION, 403), (RolUsuario.ODONTOLOGO, 403)],
)
async def test_matriz_de_roles_sobre_el_trail(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
    rol: RolUsuario,
    esperado: int,
) -> None:
    usuario = await crear_usuario(tenant_a, email=f"{rol.value}-trail@consultorio.test", rol=rol)
    await _evento(
        session,
        tenant_a,
        created_at=datetime(2026, 11, 7, 9, 0, tzinfo=UTC),
        despues={"estado": "x"},
    )

    respuesta = await api.get(URL, headers=autorizacion(token_para(usuario)))

    assert respuesta.status_code == esperado, respuesta.text
    if esperado == 403:
        assert "dueño" in respuesta.json()["detail"]
        assert "eventos" not in respuesta.json()
    else:
        assert len(respuesta.json()["eventos"]) == 1


# ---------------------------------------------------------------------------
# 2.3 Aislamiento multi-tenant del trail
# ---------------------------------------------------------------------------


async def test_el_trail_solo_devuelve_eventos_del_tenant_del_token(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    headers_a = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)
    evento_a = await _evento(
        session, tenant_a, entidad_id="de-a", created_at=datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    )
    await _evento(
        session, tenant_b, entidad_id="de-b", created_at=datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    )

    respuesta = await api.get(URL, headers=headers_a)
    assert respuesta.status_code == 200, respuesta.text
    ids = [evento["id"] for evento in respuesta.json()["eventos"]]
    assert ids == [str(evento_a.id)]

    # R4: el `tenant_id` de la query se ignora y no amplía el alcance.
    con_tenant_b = await api.get(URL, headers=headers_a, params={"tenant_id": str(tenant_b.id)})
    assert con_tenant_b.status_code == 200, con_tenant_b.text
    assert [evento["id"] for evento in con_tenant_b.json()["eventos"]] == [str(evento_a.id)]


# ---------------------------------------------------------------------------
# 2.5 Tres caminos × tres roles (trail + datasets + paquete del paciente)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "esperado"),
    [(RolUsuario.DUENO, 200), (RolUsuario.RECEPCION, 403), (RolUsuario.ODONTOLOGO, 403)],
)
async def test_tres_caminos_por_tres_roles(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
    rol: RolUsuario,
    esperado: int,
) -> None:
    """Desvío consciente de `knowledge-base/03_actores_y_roles.md:32,34` (solo Dueño).

    Consulta abierta al PO del design: si habilita exportación parcial, este test y el
    guard `requiere(Recurso.EXPORTACION_TENANT, Accion.EXPORTAR)` son el punto de rework.
    """
    usuario = await crear_usuario(tenant_a, email=f"{rol.value}-caminos@consultorio.test", rol=rol)
    headers = autorizacion(token_para(usuario))
    await _evento(
        session,
        tenant_a,
        created_at=datetime(2026, 11, 7, 9, 0, tzinfo=UTC),
        despues={"estado": "x"},
    )

    trail = await api.get(URL, headers=headers)

    assert trail.status_code == esperado, trail.text
    if esperado == 403:
        assert "dueño" in trail.json()["detail"]
        assert "eventos" not in trail.json()
    else:
        assert len(trail.json()["eventos"]) == 1


@pytest.mark.parametrize(
    ("rol", "esperado"),
    [(RolUsuario.DUENO, 200), (RolUsuario.RECEPCION, 403), (RolUsuario.ODONTOLOGO, 403)],
)
async def test_tres_caminos_por_tres_roles_datasets_y_paquete(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
    rol: RolUsuario,
    esperado: int,
) -> None:
    """Datasets (4 × CSV/JSON) y paquete del paciente: solo Dueño (desvío KB 32,34).

    Consulta abierta al PO del design: si habilita exportación parcial, este test y el
    guard `requiere(Recurso.EXPORTACION_TENANT, Accion.EXPORTAR)` son el punto de rework.
    """
    usuario = await crear_usuario(tenant_a, email=f"{rol.value}-caminos2@consultorio.test", rol=rol)
    headers = autorizacion(token_para(usuario))
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Paciente Tres Caminos",
        dni="30111222",
        telefono="1155550000",
        optin_wa=False,
        activo=True,
    )
    session.add(paciente)
    await session.flush()

    for dataset in ("agenda", "pacientes", "caja", "liquidaciones"):
        for formato in ("csv", "json"):
            resp = await api.get(
                f"/api/exportacion/{dataset}",
                headers=headers,
                params={"formato": formato},
            )
            assert resp.status_code == esperado, resp.text
            if esperado == 403:
                assert "dueño" in resp.json()["detail"]

    paquete = await api.get(f"/api/pacientes/{paciente.id}/exportar-datos", headers=headers)
    assert paquete.status_code == esperado, paquete.text
    if esperado == 403:
        assert "dueño" in paquete.json()["detail"]


async def test_periodo_por_defecto_no_depende_de_la_hora_del_cliente(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: ActorFactory,
    token_para: TokenFactory,
    autorizacion: HeaderFactory,
) -> None:
    """El nombre del archivo directo refleja el mes en curso calculado en servidor (D4)."""
    headers = await _dueno(crear_usuario, tenant_a, token_para, autorizacion)
    await _evento(session, tenant_a, created_at=datetime.now(UTC) - timedelta(minutes=1))

    respuesta = await api.get("/api/exportacion/agenda", headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    nombre = respuesta.headers["content-disposition"].split('filename="')[1].split('"')[0]
    hoy = datetime.now(UTC).astimezone(_zona_art())
    inicio_mes = hoy.replace(day=1).date().strftime("%Y%m%d")
    assert f"-{inicio_mes}_" in nombre


def _zona_art():
    """Zona ART igual que la implementación (zoneinfo con fallback UTC-3 en Windows)."""
    from app.application.exportacion import ZONA_ART

    return ZONA_ART
