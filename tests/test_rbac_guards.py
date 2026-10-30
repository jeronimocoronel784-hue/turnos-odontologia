"""Guards `requiere(recurso, accion)`: 403 accionable y sin filtrar existencia (tarea 4.2).

La matriz se evalúa en el backend: recepción no edita clínica, odontólogo no reabre
cierres de caja, recepción lee configuración pero no la modifica y el Dueño cubre
las acciones administrativas y clínicas.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
import pytest
from fastapi import APIRouter, Depends

from app.api.security import ActorAutenticado, requiere
from app.domain.rbac import Accion, Recurso
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario

PERMISO: str = "permiso"


def _router_probeas(registro: list[str]) -> APIRouter:
    """Rutas de sonda que solo registran el efecto si el guard las dejó pasar."""
    router = APIRouter(prefix="/probe")

    @router.get("/configuracion")
    async def leer_configuracion(
        actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.LEER))],
    ) -> dict[str, str]:
        registro.append(f"leer_configuracion:{actor.tenant_id}")
        return {"accion": "leer_configuracion"}

    @router.post("/configuracion")
    async def escribir_configuracion(
        actor: Annotated[
            ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.ACTUALIZAR))
        ],
    ) -> dict[str, str]:
        registro.append(f"escribir_configuracion:{actor.tenant_id}")
        return {"accion": "escribir_configuracion"}

    @router.post("/clinica/{ficha_id}")
    async def editar_clinica(
        ficha_id: str,
        actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.ACTUALIZAR))],
    ) -> dict[str, str]:
        registro.append(f"editar_clinica:{ficha_id}")
        return {"accion": "editar_clinica", "id": ficha_id}

    @router.post("/caja/{cierre_id}/reabrir")
    async def reabrir_caja(
        cierre_id: str,
        actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.REABRIR_CIERRE))],
    ) -> dict[str, str]:
        registro.append(f"reabrir_caja:{cierre_id}")
        return {"accion": "reabrir_caja", "id": cierre_id}

    return router


@asynccontextmanager
async def _cliente(app_factory, registro: list[str]) -> AsyncIterator[httpx.AsyncClient]:
    app = app_factory(_router_probeas(registro))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as cliente:
        yield cliente


async def _usuario(crear_usuario, tenant: Tenant, rol: RolUsuario, email: str) -> Usuario:
    return await crear_usuario(tenant, email=email, rol=rol)


async def test_recepcion_no_puede_editar_clinica(
    app_factory, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    recepcion = await _usuario(crear_usuario, tenant_a, RolUsuario.RECEPCION, "recepcion@x.com")
    registro: list[str] = []

    async with _cliente(app_factory, registro) as cliente:
        respuesta = await cliente.post(
            "/api/probe/clinica/ficha-1", headers=autorizacion(token_para(recepcion))
        )

    assert respuesta.status_code == 403
    assert registro == [], "la ficha clínica no debe haberse tocado"
    assert PERMISO in respuesta.json()["detail"]
    assert "dueño" in respuesta.json()["detail"]


async def test_odontologo_no_puede_reabrir_un_cierre_de_caja(
    app_factory, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    odontologo = await _usuario(crear_usuario, tenant_a, RolUsuario.ODONTOLOGO, "odonto@x.com")
    registro: list[str] = []

    async with _cliente(app_factory, registro) as cliente:
        respuesta = await cliente.post(
            "/api/probe/caja/cierre-9/reabrir", headers=autorizacion(token_para(odontologo))
        )

    assert respuesta.status_code == 403
    assert registro == [], "el cierre debe seguir cerrado"
    assert PERMISO in respuesta.json()["detail"]


async def test_recepcion_lee_configuracion_pero_no_la_modifica(
    app_factory, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    recepcion = await _usuario(crear_usuario, tenant_a, RolUsuario.RECEPCION, "recepcion@x.com")
    registro: list[str] = []

    async with _cliente(app_factory, registro) as cliente:
        lectura = await cliente.get(
            "/api/probe/configuracion", headers=autorizacion(token_para(recepcion))
        )
        escritura = await cliente.post(
            "/api/probe/configuracion", headers=autorizacion(token_para(recepcion))
        )

    assert lectura.status_code == 200
    assert lectura.json() == {"accion": "leer_configuracion"}
    assert escritura.status_code == 403
    assert registro == [f"leer_configuracion:{tenant_a.id}"]


async def test_dueno_cubre_accion_administrativa_y_clinica(
    app_factory, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    dueno = await _usuario(crear_usuario, tenant_a, RolUsuario.DUENO, "dueno@x.com")
    registro: list[str] = []

    async with _cliente(app_factory, registro) as cliente:
        admin = await cliente.post(
            "/api/probe/configuracion", headers=autorizacion(token_para(dueno))
        )
        clinica = await cliente.post(
            "/api/probe/clinica/ficha-7", headers=autorizacion(token_para(dueno))
        )

    assert admin.status_code == 200
    assert clinica.status_code == 200
    assert registro == [
        f"escribir_configuracion:{tenant_a.id}",
        "editar_clinica:ficha-7",
    ]


async def test_el_403_no_revela_si_el_recurso_existe(
    app_factory, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    recepcion = await _usuario(crear_usuario, tenant_a, RolUsuario.RECEPCION, "recepcion@x.com")
    registro: list[str] = []

    async with _cliente(app_factory, registro) as cliente:
        existente = await cliente.post(
            "/api/probe/clinica/ficha-real", headers=autorizacion(token_para(recepcion))
        )
        inexistente = await cliente.post(
            f"/api/probe/clinica/{uuid.uuid4()}", headers=autorizacion(token_para(recepcion))
        )

    assert existente.status_code == inexistente.status_code == 403
    assert existente.json() == inexistente.json()
    assert registro == []


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("get", "/api/probe/configuracion"),
        ("post", "/api/probe/configuracion"),
        ("post", "/api/probe/clinica/ficha-1"),
        ("post", "/api/probe/caja/cierre-1/reabrir"),
    ],
)
async def test_toda_ruta_con_guard_exige_token(app_factory, metodo: str, ruta: str) -> None:
    registro: list[str] = []

    async with _cliente(app_factory, registro) as cliente:
        sin_token = await cliente.request(metodo.upper(), ruta)
        token_basura = await cliente.request(
            metodo.upper(), ruta, headers={"Authorization": f"Bearer {uuid.uuid4()}"}
        )

    assert sin_token.status_code == 401
    assert token_basura.status_code == 401
    assert registro == []
