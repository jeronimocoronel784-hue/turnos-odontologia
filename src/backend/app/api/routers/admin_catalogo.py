"""Endpoints administrativos de catálogo y configuración bajo /api/admin (C-04).

R1: Schemas estrictos sin exponer ORM crudo.
R4: tenant_id viene SIEMPRE de actor.tenant_id.
R7: Soft delete en bajas lógicas (activo = False / activa = False).
RBAC: Recurso.CONFIGURACION con permisos diferenciados por rol.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api import deps
from app.api.schemas_catalogo import (
    CoberturaOSCreate,
    CoberturaOSRead,
    CoberturaOSUpdate,
    PoliticasRead,
    PoliticasUpdate,
    PrestacionCreate,
    PrestacionRead,
    PrestacionUpdate,
    SillonCreate,
    SillonRead,
    SillonUpdate,
)
from app.api.security import ActorAutenticado, requiere
from app.application.auditoria import registrar_auditoria
from app.domain.cobertura_os import CoberturaOS
from app.domain.prestacion import Prestacion
from app.domain.rbac import Accion, Recurso
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.infrastructure.db.repository import BaseRepository
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

router = APIRouter(prefix="/admin", tags=["catalogo"])


# ==========================================
# SILLONES (BOXES)
# ==========================================


@router.get("/sillones", response_model=list[SillonRead])
async def listar_sillones(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    solo_activos: bool = False,
    sucursal: str | None = None,
) -> list[Sillon]:
    """Lista sillones del consultorio del token, con filtros opcionales."""
    stmt = select(Sillon).where(Sillon.tenant_id == actor.tenant_id)
    if solo_activos:
        stmt = stmt.where(Sillon.activo.is_(True))
    if sucursal is not None:
        stmt = stmt.where(Sillon.sucursal == sucursal.strip())
    stmt = stmt.order_by(Sillon.nombre)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/sillones", response_model=SillonRead, status_code=status.HTTP_201_CREATED)
async def crear_sillon(
    datos: SillonCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Sillon:
    """Crea un sillón en el consultorio del token."""
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        nombre=datos.nombre,
        sucursal=datos.sucursal,
        activo=datos.activo,
    )
    repo = BaseRepository(session, actor.tenant_id, Sillon)
    try:
        await repo.agregar(sillon)
        await registrar_auditoria(
            session,
            tenant_id=actor.tenant_id,
            actor_id=actor.usuario_id,
            accion="sillon.crear",
            entidad="sillon",
            entidad_id=str(sillon.id),
            antes=None,
            despues={
                "nombre": sillon.nombre,
                "sucursal": sillon.sucursal,
                "activo": sillon.activo,
            },
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflicto(
            "Ya existe un sillón con ese nombre en esa sucursal de este consultorio."
        ) from exc
    return sillon


@router.patch("/sillones/{sillon_id}", response_model=SillonRead)
async def actualizar_sillon(
    sillon_id: uuid.UUID,
    datos: SillonUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Sillon:
    """Actualiza parcialmente un sillón del consultorio del token."""
    repo = BaseRepository(session, actor.tenant_id, Sillon)
    sillon = await repo.obtener(sillon_id)
    if sillon is None:
        raise NoEncontrado("No encontramos ese sillón en este consultorio.")

    antes: dict[str, object] = {
        "nombre": sillon.nombre,
        "sucursal": sillon.sucursal,
        "activo": sillon.activo,
    }

    if datos.nombre is not None:
        sillon.nombre = datos.nombre
    if datos.sucursal is not None:
        sillon.sucursal = datos.sucursal
    if datos.activo is not None:
        sillon.activo = datos.activo

    despues: dict[str, object] = {
        "nombre": sillon.nombre,
        "sucursal": sillon.sucursal,
        "activo": sillon.activo,
    }

    try:
        await registrar_auditoria(
            session,
            tenant_id=actor.tenant_id,
            actor_id=actor.usuario_id,
            accion="sillon.actualizar",
            entidad="sillon",
            entidad_id=str(sillon.id),
            antes=antes,
            despues=despues,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflicto(
            "Ya existe un sillón con ese nombre en esa sucursal de este consultorio."
        ) from exc
    return sillon


@router.delete("/sillones/{sillon_id}", response_model=SillonRead)
async def desactivar_sillon(
    sillon_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.BORRAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Sillon:
    """Baja lógica de un sillón (activo = False, nunca hard delete)."""
    repo = BaseRepository(session, actor.tenant_id, Sillon)
    sillon = await repo.obtener(sillon_id)
    if sillon is None:
        raise NoEncontrado("No encontramos ese sillón en este consultorio.")

    antes: dict[str, object] = {"activo": sillon.activo}
    sillon.activo = False
    despues: dict[str, object] = {"activo": False}

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="sillon.desactivar",
        entidad="sillon",
        entidad_id=str(sillon.id),
        antes=antes,
        despues=despues,
    )
    await session.commit()
    return sillon


# ==========================================
# PRESTACIONES
# ==========================================


@router.get("/prestaciones", response_model=list[PrestacionRead])
async def listar_prestaciones(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    solo_activas: bool = False,
) -> list[Prestacion]:
    """Lista prestaciones del consultorio del token, con filtros opcionales."""
    stmt = select(Prestacion).where(Prestacion.tenant_id == actor.tenant_id)
    if solo_activas:
        stmt = stmt.where(Prestacion.activa.is_(True))
    stmt = stmt.order_by(Prestacion.nombre)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/prestaciones", response_model=PrestacionRead, status_code=status.HTTP_201_CREATED)
async def crear_prestacion(
    datos: PrestacionCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Prestacion:
    """Crea una prestación en el consultorio del token."""
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        nombre=datos.nombre,
        duracion_min=datos.duracion_min,
        precio_particular=datos.precio_particular,
        requiere_sena=datos.requiere_sena,
        monto_sena=datos.monto_sena,
        invasiva=datos.invasiva,
        activa=datos.activa,
    )
    repo = BaseRepository(session, actor.tenant_id, Prestacion)
    try:
        await repo.agregar(prestacion)
        await registrar_auditoria(
            session,
            tenant_id=actor.tenant_id,
            actor_id=actor.usuario_id,
            accion="prestacion.crear",
            entidad="prestacion",
            entidad_id=str(prestacion.id),
            antes=None,
            despues={
                "nombre": prestacion.nombre,
                "duracion_min": prestacion.duracion_min,
                "precio_particular": str(prestacion.precio_particular),
                "requiere_sena": prestacion.requiere_sena,
                "monto_sena": str(prestacion.monto_sena) if prestacion.monto_sena else None,
                "invasiva": prestacion.invasiva,
                "activa": prestacion.activa,
            },
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflicto("Ya existe una prestación con ese nombre en este consultorio.") from exc
    return prestacion


@router.patch("/prestaciones/{prestacion_id}", response_model=PrestacionRead)
async def actualizar_prestacion(
    prestacion_id: uuid.UUID,
    datos: PrestacionUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Prestacion:
    """Actualiza parcialmente una prestación del consultorio del token."""
    repo = BaseRepository(session, actor.tenant_id, Prestacion)
    prestacion = await repo.obtener(prestacion_id)
    if prestacion is None:
        raise NoEncontrado("No encontramos esa prestación en este consultorio.")

    antes: dict[str, object] = {
        "nombre": prestacion.nombre,
        "duracion_min": prestacion.duracion_min,
        "precio_particular": str(prestacion.precio_particular),
        "requiere_sena": prestacion.requiere_sena,
        "monto_sena": str(prestacion.monto_sena) if prestacion.monto_sena else None,
        "invasiva": prestacion.invasiva,
        "activa": prestacion.activa,
    }

    # Validación de estado combinado para requiere_sena y monto_sena
    nueva_requiere_sena = (
        datos.requiere_sena if datos.requiere_sena is not None else prestacion.requiere_sena
    )
    nuevo_monto_sena = datos.monto_sena if datos.monto_sena is not None else prestacion.monto_sena

    if nueva_requiere_sena:
        if nuevo_monto_sena is None or nuevo_monto_sena <= Decimal("0.00"):
            raise EntidadInvalida(
                "Che, tenés que informar un monto de seña mayor a cero "
                "cuando la prestación requiere seña."
            )
    else:
        nuevo_monto_sena = None

    if datos.nombre is not None:
        prestacion.nombre = datos.nombre
    if datos.duracion_min is not None:
        prestacion.duracion_min = datos.duracion_min
    if datos.precio_particular is not None:
        prestacion.precio_particular = datos.precio_particular
    prestacion.requiere_sena = nueva_requiere_sena
    prestacion.monto_sena = nuevo_monto_sena
    if datos.invasiva is not None:
        prestacion.invasiva = datos.invasiva
    if datos.activa is not None:
        prestacion.activa = datos.activa

    despues: dict[str, object] = {
        "nombre": prestacion.nombre,
        "duracion_min": prestacion.duracion_min,
        "precio_particular": str(prestacion.precio_particular),
        "requiere_sena": prestacion.requiere_sena,
        "monto_sena": str(prestacion.monto_sena) if prestacion.monto_sena else None,
        "invasiva": prestacion.invasiva,
        "activa": prestacion.activa,
    }

    try:
        await registrar_auditoria(
            session,
            tenant_id=actor.tenant_id,
            actor_id=actor.usuario_id,
            accion="prestacion.actualizar",
            entidad="prestacion",
            entidad_id=str(prestacion.id),
            antes=antes,
            despues=despues,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflicto("Ya existe una prestación con ese nombre en este consultorio.") from exc
    return prestacion


@router.delete("/prestaciones/{prestacion_id}", response_model=PrestacionRead)
async def desactivar_prestacion(
    prestacion_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.BORRAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Prestacion:
    """Baja lógica de una prestación (activa = False, nunca hard delete)."""
    repo = BaseRepository(session, actor.tenant_id, Prestacion)
    prestacion = await repo.obtener(prestacion_id)
    if prestacion is None:
        raise NoEncontrado("No encontramos esa prestación en este consultorio.")

    antes: dict[str, object] = {"activa": prestacion.activa}
    prestacion.activa = False
    despues: dict[str, object] = {"activa": False}

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="prestacion.desactivar",
        entidad="prestacion",
        entidad_id=str(prestacion.id),
        antes=antes,
        despues=despues,
    )
    await session.commit()
    return prestacion


# ==========================================
# COBERTURAS OBRA SOCIAL
# ==========================================


@router.get("/coberturas", response_model=list[CoberturaOSRead])
async def listar_coberturas(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    vigente_en: date | None = None,
    obra_social: str | None = None,
    prestacion_id: uuid.UUID | None = None,
    solo_activas: bool = False,
) -> list[CoberturaOS]:
    """Lista convenios de obra social del consultorio con filtros opcionales."""
    stmt = select(CoberturaOS).where(CoberturaOS.tenant_id == actor.tenant_id)
    if vigente_en is not None:
        stmt = stmt.where(
            CoberturaOS.activa.is_(True),
            CoberturaOS.vigencia_desde <= vigente_en,
            (CoberturaOS.vigencia_hasta.is_(None) | (CoberturaOS.vigencia_hasta >= vigente_en)),
        )
    elif solo_activas:
        stmt = stmt.where(CoberturaOS.activa.is_(True))

    if obra_social is not None:
        stmt = stmt.where(CoberturaOS.obra_social == obra_social.strip())
    if prestacion_id is not None:
        stmt = stmt.where(CoberturaOS.prestacion_id == prestacion_id)

    stmt = stmt.order_by(CoberturaOS.obra_social, CoberturaOS.vigencia_desde.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("/coberturas", response_model=CoberturaOSRead, status_code=status.HTTP_201_CREATED)
async def crear_cobertura(
    datos: CoberturaOSCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> CoberturaOS:
    """Crea un convenio con obra social validando pertenencia de la prestación al consultorio."""
    prestacion = await BaseRepository(session, actor.tenant_id, Prestacion).obtener(
        datos.prestacion_id
    )
    if prestacion is None:
        raise NoEncontrado("No encontramos esa prestación en este consultorio.")

    cobertura = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        obra_social=datos.obra_social,
        prestacion_id=datos.prestacion_id,
        arancel=datos.arancel,
        copago=datos.copago,
        vigencia_desde=datos.vigencia_desde,
        vigencia_hasta=datos.vigencia_hasta,
        activa=datos.activa,
    )
    repo = BaseRepository(session, actor.tenant_id, CoberturaOS)
    await repo.agregar(cobertura)

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="cobertura_os.crear",
        entidad="cobertura_os",
        entidad_id=str(cobertura.id),
        antes=None,
        despues={
            "obra_social": cobertura.obra_social,
            "prestacion_id": str(cobertura.prestacion_id),
            "arancel": str(cobertura.arancel),
            "copago": str(cobertura.copago),
            "vigencia_desde": str(cobertura.vigencia_desde),
            "vigencia_hasta": str(cobertura.vigencia_hasta) if cobertura.vigencia_hasta else None,
            "activa": cobertura.activa,
        },
    )
    await session.commit()
    return cobertura


@router.patch("/coberturas/{cobertura_id}", response_model=CoberturaOSRead)
async def actualizar_cobertura(
    cobertura_id: uuid.UUID,
    datos: CoberturaOSUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> CoberturaOS:
    """Actualiza parcialmente un convenio con obra social validando consistencia de vigencia."""
    repo = BaseRepository(session, actor.tenant_id, CoberturaOS)
    cobertura = await repo.obtener(cobertura_id)
    if cobertura is None:
        raise NoEncontrado("No encontramos esa cobertura en este consultorio.")

    # Validación de vigencia combinada
    nueva_desde = (
        datos.vigencia_desde if datos.vigencia_desde is not None else cobertura.vigencia_desde
    )
    nueva_hasta = (
        datos.vigencia_hasta if datos.vigencia_hasta is not None else cobertura.vigencia_hasta
    )
    if nueva_hasta is not None and nueva_hasta < nueva_desde:
        raise EntidadInvalida(
            "Che, la vigencia hasta debe ser posterior o igual a la vigencia desde."
        )

    antes: dict[str, object] = {
        "obra_social": cobertura.obra_social,
        "arancel": str(cobertura.arancel),
        "copago": str(cobertura.copago),
        "vigencia_desde": str(cobertura.vigencia_desde),
        "vigencia_hasta": str(cobertura.vigencia_hasta) if cobertura.vigencia_hasta else None,
        "activa": cobertura.activa,
    }

    if datos.obra_social is not None:
        cobertura.obra_social = datos.obra_social
    if datos.arancel is not None:
        cobertura.arancel = datos.arancel
    if datos.copago is not None:
        cobertura.copago = datos.copago
    if datos.vigencia_desde is not None:
        cobertura.vigencia_desde = datos.vigencia_desde
    if datos.vigencia_hasta is not None:
        cobertura.vigencia_hasta = datos.vigencia_hasta
    if datos.activa is not None:
        cobertura.activa = datos.activa

    despues: dict[str, object] = {
        "obra_social": cobertura.obra_social,
        "arancel": str(cobertura.arancel),
        "copago": str(cobertura.copago),
        "vigencia_desde": str(cobertura.vigencia_desde),
        "vigencia_hasta": str(cobertura.vigencia_hasta) if cobertura.vigencia_hasta else None,
        "activa": cobertura.activa,
    }

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="cobertura_os.actualizar",
        entidad="cobertura_os",
        entidad_id=str(cobertura.id),
        antes=antes,
        despues=despues,
    )
    await session.commit()
    return cobertura


@router.delete("/coberturas/{cobertura_id}", response_model=CoberturaOSRead)
async def desactivar_cobertura(
    cobertura_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.BORRAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> CoberturaOS:
    """Baja lógica de un convenio de obra social (activa = False, nunca hard delete)."""
    repo = BaseRepository(session, actor.tenant_id, CoberturaOS)
    cobertura = await repo.obtener(cobertura_id)
    if cobertura is None:
        raise NoEncontrado("No encontramos esa cobertura en este consultorio.")

    antes: dict[str, object] = {"activa": cobertura.activa}
    cobertura.activa = False
    despues: dict[str, object] = {"activa": False}

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="cobertura_os.desactivar",
        entidad="cobertura_os",
        entidad_id=str(cobertura.id),
        antes=antes,
        despues=despues,
    )
    await session.commit()
    return cobertura


# ==========================================
# POLÍTICAS OPERATIVAS DEL CONSULTORIO
# ==========================================


def _a_int(valor: object, defecto: int) -> int:
    if valor is None:
        return defecto
    try:
        return int(str(valor))
    except (ValueError, TypeError):
        return defecto


def _a_int_opcional(valor: object) -> int | None:
    if valor is None:
        return None
    try:
        return int(str(valor))
    except (ValueError, TypeError):
        return None


@router.get("/tenant/politicas", response_model=PoliticasRead)
async def obtener_politicas_tenant(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PoliticasRead:
    """Consulta las políticas operativas del consultorio del token con defaults seguros."""
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == actor.tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise NoEncontrado("No encontramos el consultorio.")

    politicas = tenant.politicas or {}
    return PoliticasRead(
        anticipacion_min_dias=_a_int(politicas.get("anticipacion_min_dias"), 1),
        sena_default_pct=_a_int(politicas.get("sena_default_pct"), 30),
        cancelacion_horas=_a_int(politicas.get("cancelacion_horas"), 24),
        anticipacion_min_hs=_a_int_opcional(politicas.get("anticipacion_min_hs")),
    )


@router.patch("/tenant/politicas", response_model=PoliticasRead)
async def actualizar_politicas_tenant(
    datos: PoliticasUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONFIGURACION, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PoliticasRead:
    """Actualiza parcialmente las políticas operativas del consultorio del token."""
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == actor.tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise NoEncontrado("No encontramos el consultorio.")

    antes: dict[str, object] = dict(tenant.politicas or {})
    nuevas: dict[str, object] = dict(tenant.politicas or {})

    if datos.anticipacion_min_dias is not None:
        nuevas["anticipacion_min_dias"] = datos.anticipacion_min_dias
    if datos.sena_default_pct is not None:
        nuevas["sena_default_pct"] = datos.sena_default_pct
    if datos.cancelacion_horas is not None:
        nuevas["cancelacion_horas"] = datos.cancelacion_horas
    if datos.anticipacion_min_hs is not None:
        nuevas["anticipacion_min_hs"] = datos.anticipacion_min_hs

    tenant.politicas = nuevas
    flag_modified(tenant, "politicas")

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="tenant.actualizar_politicas",
        entidad="tenant",
        entidad_id=str(tenant.id),
        antes=antes,
        despues=nuevas,
    )
    await session.commit()

    return PoliticasRead(
        anticipacion_min_dias=_a_int(nuevas.get("anticipacion_min_dias"), 1),
        sena_default_pct=_a_int(nuevas.get("sena_default_pct"), 30),
        cancelacion_horas=_a_int(nuevas.get("cancelacion_horas"), 24),
        anticipacion_min_hs=_a_int_opcional(nuevas.get("anticipacion_min_hs")),
    )
