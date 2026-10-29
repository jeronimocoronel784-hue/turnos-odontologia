"""Endpoints internos de usuarios: CRUD de staff con guards RBAC (C-03, tarea 4.3)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas import UsuarioCreate, UsuarioRead
from app.api.schemas_auth import RolUpdate
from app.api.security import ActorAutenticado, requiere
from app.application.auditoria import registrar_auditoria
from app.domain.rbac import Accion, Recurso
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.repository import BaseRepository
from app.infrastructure.security.passwords import hashear_password
from app.shared.exceptions import Conflicto, NoEncontrado, SolicitudInvalida
from app.shared.settings import Settings

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.USUARIOS, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> list[Usuario]:
    """Lista solo los usuarios del tenant del token (R4)."""
    return await BaseRepository(session, actor.tenant_id, Usuario).listar()


@router.post("", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def crear_usuario(
    datos: UsuarioCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.USUARIOS, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
) -> Usuario:
    """Alta de staff en el tenant del token; email repetido en el tenant es 409."""
    usuario = Usuario(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        email=str(datos.email),
        nombre=datos.nombre,
        rol=datos.rol,
        matricula=datos.matricula,
        password_hash=hashear_password(datos.password, settings.bcrypt_rounds),
        activo=True,
    )
    session.add(usuario)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflicto("Ese email ya está usado en este consultorio. Probá con otro.") from exc

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="usuario.crear",
        entidad="usuario",
        entidad_id=str(usuario.id),
        despues={"rol": datos.rol.value},
    )
    await session.commit()
    return usuario


@router.patch("/{usuario_id}/rol", response_model=UsuarioRead)
async def cambiar_rol(
    usuario_id: uuid.UUID,
    datos: RolUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.USUARIOS, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Usuario:
    """Cambia rol/matrícula dentro del tenant y deja rastro en auditoría."""
    usuario = await BaseRepository(session, actor.tenant_id, Usuario).obtener(usuario_id)
    if usuario is None:
        raise NoEncontrado("No encontramos ese usuario en este consultorio.")
    if usuario.rol == RolUsuario.DUENO and datos.rol != RolUsuario.DUENO:
        otros_duenos = [
            otro
            for otro in await BaseRepository(session, actor.tenant_id, Usuario).listar()
            if otro.rol == RolUsuario.DUENO and otro.id != usuario.id and otro.activo
        ]
        if not otros_duenos:
            raise SolicitudInvalida(
                "El consultorio necesita al menos un dueño activo. "
                "Asigná otro antes de cambiar este."
            )

    antes: dict[str, object] = {"rol": str(usuario.rol), "matricula": usuario.matricula}
    usuario.rol = datos.rol
    usuario.matricula = datos.matricula
    await session.flush()
    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="usuario.cambiar_rol",
        entidad="usuario",
        entidad_id=str(usuario.id),
        antes=antes,
        despues={"rol": datos.rol.value, "matricula": datos.matricula},
    )
    await session.commit()
    return usuario
