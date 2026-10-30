"""Matriz RBAC declarativa y tenant efectivo del token (tarea 4.1).

Espejo de `knowledge-base/03_actores_y_roles.md`: toda operación interna se valida
contra esta tabla en el backend (no en la UI). `roles` es lista para no romper el
contrato cuando exista multi-rol real (D5).
"""

import uuid

import pytest

from app.api.security import ActorAutenticado
from app.domain.rbac import MATRIZ, Accion, Recurso, permite
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.repository import BaseRepository

CRUD = frozenset({Accion.LEER, Accion.CREAR, Accion.ACTUALIZAR, Accion.BORRAR})
R = frozenset({Accion.LEER})
N = frozenset()
DUENO = RolUsuario.DUENO.value
RECEPCION = RolUsuario.RECEPCION.value
ODONTOLOGO = RolUsuario.ODONTOLOGO.value

# Copia explícita de la matriz de §03 (independiente del código: si alguien toca
# `app/domain/rbac.py` sin actualizar la KB, este test lo delata).
ESPERADO: dict[Recurso, dict[str, frozenset[Accion]]] = {
    Recurso.CONFIGURACION: {DUENO: CRUD, RECEPCION: R, ODONTOLOGO: R},
    Recurso.USUARIOS: {DUENO: CRUD, RECEPCION: R, ODONTOLOGO: R},
    Recurso.PACIENTES: {DUENO: CRUD, RECEPCION: CRUD, ODONTOLOGO: R},
    Recurso.AGENDA: {
        DUENO: CRUD,
        RECEPCION: CRUD,
        ODONTOLOGO: frozenset({Accion.LEER, Accion.ACTUALIZAR}),
    },
    Recurso.BLOQUEOS: {DUENO: CRUD, RECEPCION: CRUD, ODONTOLOGO: R},
    Recurso.LISTA_ESPERA: {DUENO: CRUD, RECEPCION: CRUD, ODONTOLOGO: R},
    Recurso.CLINICA: {DUENO: CRUD, RECEPCION: R, ODONTOLOGO: CRUD},
    Recurso.PRESUPUESTOS: {DUENO: CRUD, RECEPCION: CRUD, ODONTOLOGO: CRUD},
    Recurso.CONSENTIMIENTOS: {DUENO: CRUD, RECEPCION: CRUD, ODONTOLOGO: CRUD},
    Recurso.CAJA: {
        DUENO: frozenset({*CRUD, Accion.REABRIR_CIERRE}),
        RECEPCION: CRUD,
        ODONTOLOGO: R,
    },
    Recurso.LIQUIDACIONES: {DUENO: CRUD, RECEPCION: CRUD, ODONTOLOGO: R},
    Recurso.MENSAJES: {
        DUENO: CRUD,
        RECEPCION: frozenset({Accion.LEER, Accion.REENVIAR}),
        ODONTOLOGO: N,
    },
    Recurso.AUDITORIA: {DUENO: R, RECEPCION: N, ODONTOLOGO: N},
    Recurso.EXPORTACION: {
        DUENO: frozenset({Accion.EXPORTAR}),
        RECEPCION: frozenset({Accion.EXPORTAR}),
        ODONTOLOGO: frozenset({Accion.EXPORTAR}),
    },
}


def test_la_matriz_espeja_la_kb_completa() -> None:
    actual = {
        recurso: {rol: set(acciones) for rol, acciones in por_rol.items()}
        for recurso, por_rol in MATRIZ.items()
    }
    esperado = {
        recurso: {rol: set(acciones) for rol, acciones in por_rol.items()}
        for recurso, por_rol in ESPERADO.items()
    }

    assert actual == esperado


def test_todos_los_recursos_cubren_los_tres_roles() -> None:
    for recurso in Recurso:
        assert set(MATRIZ[recurso]) == {DUENO, RECEPCION, ODONTOLOGO}, recurso
    assert set(MATRIZ) == set(Recurso)


def test_permite_evalua_multirrol_y_no_regala_permisos() -> None:
    # Dueño + odontólogo (doble rol operativo): cada rol aporta lo suyo.
    assert permite([DUENO, ODONTOLOGO], Recurso.CAJA, Accion.REABRIR_CIERRE) is True
    assert permite([DUENO, ODONTOLOGO], Recurso.CONFIGURACION, Accion.ACTUALIZAR) is True
    # Rol solo: no puede lo que no está en su fila.
    assert permite([RECEPCION], Recurso.CAJA, Accion.REABRIR_CIERRE) is False
    assert permite([ODONTOLOGO], Recurso.MENSAJES, Accion.LEER) is False
    # Rol desconocido o vacío: nunca concede.
    assert permite(["rol-inventado"], Recurso.USUARIOS, Accion.LEER) is False
    assert permite([], Recurso.USUARIOS, Accion.LEER) is False


def test_actor_autenticado_declara_solo_lo_del_token() -> None:
    actor = ActorAutenticado(
        usuario_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="staff@example.com",
        nombre="Staff",
        roles=(RolUsuario.RECEPCION,),
    )

    assert [rol.value for rol in actor.roles] == ["recepcion"]
    assert permite((rol.value for rol in actor.roles), Recurso.USUARIOS, Accion.LEER)


async def test_el_tenant_efectivo_sale_del_token_y_no_de_la_query(
    api, session, tenant_a: Tenant, tenant_b: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    en_a: Usuario = await crear_usuario(tenant_a, email="a@example.com")
    await crear_usuario(tenant_b, email="b@example.com")
    token = token_para(en_a)

    # Aunque el cliente pida el tenant B por query, se responde con el del token.
    respuesta = await api.get(f"/api/usuarios?tenant_id={tenant_b.id}", headers=autorizacion(token))

    assert respuesta.status_code == 200
    assert {u["email"] for u in respuesta.json()} == {"a@example.com"}
    assert all(u["tenant_id"] == str(tenant_a.id) for u in respuesta.json())

    # Y el repositorio del tenant A no ve al usuario de B ni por id directo.
    intruso = (await BaseRepository(session, tenant_b.id, Usuario).listar())[0]
    assert await BaseRepository(session, tenant_a.id, Usuario).obtener(intruso.id) is None


@pytest.mark.parametrize("rol", list(RolUsuario))
async def test_cada_rol_puede_leer_usuarios_de_su_tenant(
    api, tenant_a: Tenant, crear_usuario, token_para, autorizacion, rol: RolUsuario
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=f"{rol.value}@example.com", rol=rol)

    respuesta = await api.get("/api/usuarios", headers=autorizacion(token_para(usuario)))

    assert respuesta.status_code == 200
    assert [u["id"] for u in respuesta.json()] == [str(usuario.id)]
