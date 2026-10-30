"""Endpoints /api/usuarios: CRUD con guards, tenant del token y auditoría (tareas 4.3 y 4.4)."""

import uuid

from sqlalchemy import select

from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.repository import BaseRepository

DUENO_EMAIL = "dueno@example.com"
RECEPCION_EMAIL = "recepcion@example.com"
ODONTOLOGO_EMAIL = "odonto@example.com"


async def _tres_roles(tenant_a: Tenant, crear_usuario) -> dict[RolUsuario, Usuario]:
    return {
        RolUsuario.DUENO: await crear_usuario(
            tenant_a, email=DUENO_EMAIL, rol=RolUsuario.DUENO, nombre="Dueña"
        ),
        RolUsuario.RECEPCION: await crear_usuario(
            tenant_a, email=RECEPCION_EMAIL, rol=RolUsuario.RECEPCION, nombre="Recep"
        ),
        RolUsuario.ODONTOLOGO: await crear_usuario(
            tenant_a, email=ODONTOLOGO_EMAIL, rol=RolUsuario.ODONTOLOGO, nombre="Odonto"
        ),
    }


async def test_solo_se_leen_usuarios_del_tenant_del_token(
    api, tenant_a: Tenant, tenant_b: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    usuario_a: Usuario = await crear_usuario(tenant_a, email="a@example.com")
    usuario_b: Usuario = await crear_usuario(tenant_b, email="b@example.com")

    respuesta = await api.get("/api/usuarios", headers=autorizacion(token_para(usuario_a)))

    assert respuesta.status_code == 200
    emails = {u["email"] for u in respuesta.json()}
    assert emails == {"a@example.com"}
    assert usuario_b.email not in respuesta.text
    assert all(u["tenant_id"] == str(tenant_a.id) for u in respuesta.json())


async def test_alta_de_usuario_solo_para_dueno_y_auditada(
    api, session, tenant_a: Tenant, crear_usuario, token_para, autorizacion, auditoria_de
) -> None:
    roles = await _tres_roles(tenant_a, crear_usuario)
    datos = {
        "email": "nueva@example.com",
        "nombre": "Persona Nueva",
        "rol": "recepcion",
        "password": "contrasena-larga-1",
    }

    recepcion = await api.post(
        "/api/usuarios", json=datos, headers=autorizacion(token_para(roles[RolUsuario.RECEPCION]))
    )
    odontologo = await api.post(
        "/api/usuarios", json=datos, headers=autorizacion(token_para(roles[RolUsuario.ODONTOLOGO]))
    )
    dueno = await api.post(
        "/api/usuarios", json=datos, headers=autorizacion(token_para(roles[RolUsuario.DUENO]))
    )

    assert recepcion.status_code == 403
    assert odontologo.status_code == 403
    assert dueno.status_code == 201
    creada = dueno.json()
    assert creada["email"] == "nueva@example.com"
    assert creada["tenant_id"] == str(tenant_a.id)
    assert creada["rol"] == "recepcion"
    assert "password" not in dueno.text
    assert "password_hash" not in dueno.text

    eventos = await auditoria_de("usuario.crear")
    assert len(eventos) == 1
    assert eventos[0].actor_id == roles[RolUsuario.DUENO].id
    assert eventos[0].entidad_id == creada["id"]
    assert eventos[0].despues == {"rol": "recepcion"}
    assert "contrasena-larga-1" not in f"{eventos[0].antes}{eventos[0].despues}"

    creados = await BaseRepository(session, tenant_a.id, Usuario).listar()
    assert len(creados) == 4


async def test_alta_con_tenant_id_en_el_body_se_rechaza(
    api, tenant_a: Tenant, tenant_b: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    dueno: Usuario = await crear_usuario(tenant_a, email=DUENO_EMAIL, rol=RolUsuario.DUENO)

    respuesta = await api.post(
        "/api/usuarios",
        json={
            "email": "intrusa@example.com",
            "nombre": "Intrusa",
            "rol": "odontologo",
            "matricula": "MP-9",
            "password": "contrasena-larga-1",
            "tenant_id": str(tenant_b.id),
        },
        headers=autorizacion(token_para(dueno)),
    )

    assert respuesta.status_code == 422
    assert "tenant_id" in respuesta.text


async def test_email_repetido_en_el_tenant_es_409(
    api, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    dueno: Usuario = await crear_usuario(tenant_a, email=DUENO_EMAIL, rol=RolUsuario.DUENO)
    await crear_usuario(tenant_a, email="repetida@example.com")

    respuesta = await api.post(
        "/api/usuarios",
        json={
            "email": "repetida@example.com",
            "nombre": "Otra",
            "rol": "recepcion",
            "password": "contrasena-larga-1",
        },
        headers=autorizacion(token_para(dueno)),
    )

    assert respuesta.status_code == 409
    assert "ya está usado" in respuesta.json()["detail"]


async def test_alta_con_password_multibyte_da_400_y_no_500(
    api, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    dueno: Usuario = await crear_usuario(tenant_a, email=DUENO_EMAIL, rol=RolUsuario.DUENO)

    respuesta = await api.post(
        "/api/usuarios",
        json={
            "email": "emoji@example.com",
            "nombre": "Emoji",
            "rol": "recepcion",
            "password": "🙂" * 30,  # 30 caracteres, 120 bytes: excede el límite de bcrypt
        },
        headers=autorizacion(token_para(dueno)),
    )

    assert respuesta.status_code == 400
    assert "72" in respuesta.json()["detail"]
    assert "Traceback" not in respuesta.text


async def test_cambio_de_rol_solo_dueno_y_queda_auditado(
    api, tenant_a: Tenant, crear_usuario, token_para, autorizacion, auditoria_de
) -> None:
    roles = await _tres_roles(tenant_a, crear_usuario)
    objetivo = roles[RolUsuario.RECEPCION]

    recepcion = await api.patch(
        f"/api/usuarios/{objetivo.id}/rol",
        json={"rol": "odontologo", "matricula": "MP-4321"},
        headers=autorizacion(token_para(roles[RolUsuario.RECEPCION])),
    )
    dueno = await api.patch(
        f"/api/usuarios/{objetivo.id}/rol",
        json={"rol": "odontologo", "matricula": "MP-4321"},
        headers=autorizacion(token_para(roles[RolUsuario.DUENO])),
    )

    assert recepcion.status_code == 403
    assert dueno.status_code == 200
    assert dueno.json()["rol"] == "odontologo"
    assert dueno.json()["matricula"] == "MP-4321"

    eventos = await auditoria_de("usuario.cambiar_rol")
    assert len(eventos) == 1
    assert eventos[0].actor_id == roles[RolUsuario.DUENO].id
    assert eventos[0].entidad_id == str(objetivo.id)
    assert eventos[0].antes == {"rol": "recepcion", "matricula": None}
    assert eventos[0].despues == {"rol": "odontologo", "matricula": "MP-4321"}


async def test_cambio_de_rol_valida_matricula_y_ultimo_dueno(
    api, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    roles = await _tres_roles(tenant_a, crear_usuario)
    token_dueno = autorizacion(token_para(roles[RolUsuario.DUENO]))

    sin_matricula = await api.patch(
        f"/api/usuarios/{roles[RolUsuario.RECEPCION].id}/rol",
        json={"rol": "odontologo"},
        headers=token_dueno,
    )
    ultimo_dueno = await api.patch(
        f"/api/usuarios/{roles[RolUsuario.DUENO].id}/rol",
        json={"rol": "recepcion"},
        headers=token_dueno,
    )

    assert sin_matricula.status_code == 422
    assert ultimo_dueno.status_code == 400
    assert "dueño activo" in ultimo_dueno.json()["detail"]

    # El rol del dueño no cambió: sigue siendo el único dueño del consultorio.
    listado = (await api.get("/api/usuarios", headers=token_dueno)).json()
    assert any(u["rol"] == "dueno" for u in listado)


async def test_cambio_de_rol_de_usuario_inexistente_o_de_otro_tenant_es_404(
    api, tenant_a: Tenant, tenant_b: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    dueno: Usuario = await crear_usuario(tenant_a, email=DUENO_EMAIL, rol=RolUsuario.DUENO)
    ajeno: Usuario = await crear_usuario(tenant_b, email="ajeno@example.com")
    headers = autorizacion(token_para(dueno))

    inexistente = await api.patch(
        f"/api/usuarios/{uuid.uuid4()}/rol", json={"rol": "recepcion"}, headers=headers
    )
    de_otro = await api.patch(
        f"/api/usuarios/{ajeno.id}/rol", json={"rol": "recepcion"}, headers=headers
    )

    assert inexistente.status_code == 404
    assert de_otro.status_code == 404
    assert inexistente.json() == de_otro.json()


async def test_las_rutas_de_usuarios_exigen_token(api) -> None:
    respuestas = [
        await api.get("/api/usuarios"),
        await api.post("/api/usuarios", json={}),
        await api.patch(f"/api/usuarios/{uuid.uuid4()}/rol", json={"rol": "recepcion"}),
    ]

    assert [r.status_code for r in respuestas] == [401, 401, 401]


async def test_el_listado_no_expone_el_hash(
    api, session, tenant_a: Tenant, crear_usuario, token_para, autorizacion
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email="a@example.com")
    respuesta = await api.get("/api/usuarios", headers=autorizacion(token_para(usuario)))

    assert usuario.password_hash not in respuesta.text
    assert "password_hash" not in respuesta.text
    filas = list((await session.execute(select(Usuario))).scalars().all())
    assert all(fila.password_hash.startswith("$2b$") for fila in filas)
