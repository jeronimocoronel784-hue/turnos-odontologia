"""Routers de Lista de Espera: gestión interna (`/api/lista-espera`) y pública (`/lista-espera`).

Reglas implementadas:
- RN-LE-01: listado y oferta en orden estricto `(prioridad ASC, created_at ASC)`.
- RN-LE-02: idempotencia por `(entrada, hueco)` y rotación al vencer ventana.
- RN-LE-03: aceptación por token opaco crea `Turno` y marca `colocada`.
- R4 / RN-SE-03: RBAC (`Recurso.LISTA_ESPERA`) en rutas internas y token opaco en públicas.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_lista_espera import (
    ListaEsperaCreate,
    ListaEsperaPublicaCreate,
    ListaEsperaPublicaRead,
    ListaEsperaRead,
    ListaEsperaUpdate,
    OfrecerHuecoRequest,
)
from app.api.security import ActorAutenticado, requiere
from app.application.auditoria import registrar_auditoria
from app.application.lista_espera import (
    aceptar_oferta_lista_espera,
    crear_entrada_lista_espera,
    dar_baja_lista_espera,
    ofrecer_hueco_lista_espera,
)
from app.application.pacientes import get_or_create_paciente
from app.domain.lista_espera import CanalAviso, EstadoListaEspera, ListaEspera
from app.domain.prestacion import Prestacion
from app.domain.rbac import Accion, Recurso
from app.domain.tenant import Tenant
from app.domain.usuario import Usuario
from app.infrastructure.security.tokens_publicos import (
    marcar_usado,
    resolver_token_gestion_recurso,
)
from app.shared.exceptions import EntidadInvalida, NoEncontrado

router = APIRouter(tags=["lista-espera"])
router_publico = APIRouter(tags=["lista-espera-publica"])


def _serializar_entrada(
    entrada: ListaEspera,
    token_gestion: str | None = None,
) -> ListaEsperaRead:
    return ListaEsperaRead(
        id=entrada.id,
        tenant_id=entrada.tenant_id,
        paciente_id=entrada.paciente_id,
        prestacion_id=entrada.prestacion_id,
        profesional_id=entrada.profesional_id,
        prioridad=entrada.prioridad,
        estado=EstadoListaEspera(entrada.estado),
        canal_aviso=CanalAviso(entrada.canal_aviso),
        observaciones=entrada.observaciones,
        hueco_inicio=entrada.hueco_inicio,
        hueco_fin=entrada.hueco_fin,
        hueco_profesional_id=entrada.hueco_profesional_id,
        hueco_sillon_id=entrada.hueco_sillon_id,
        aviso_vence_at=entrada.aviso_vence_at,
        ultimo_idempotency_key=entrada.ultimo_idempotency_key,
        turno_colocado_id=entrada.turno_colocado_id,
        created_at=entrada.created_at,
        updated_at=entrada.updated_at,
        token_gestion=token_gestion,
    )


async def _armar_respuesta_publica_le(
    session: AsyncSession,
    entrada: ListaEspera,
    *,
    token_gestion: str | None = None,
) -> ListaEsperaPublicaRead:
    prestacion = await session.get(Prestacion, entrada.prestacion_id)
    prof_id = entrada.hueco_profesional_id or entrada.profesional_id
    profesional = await session.get(Usuario, prof_id) if prof_id else None
    return ListaEsperaPublicaRead(
        entrada_id=entrada.id,
        estado=EstadoListaEspera(entrada.estado),
        prestacion_id=entrada.prestacion_id,
        prestacion_nombre=prestacion.nombre if prestacion else "",
        profesional_id=prof_id,
        profesional_nombre=profesional.nombre if profesional else None,
        canal_aviso=CanalAviso(entrada.canal_aviso),
        hueco_inicio=entrada.hueco_inicio,
        hueco_fin=entrada.hueco_fin,
        aviso_vence_at=entrada.aviso_vence_at,
        turno_colocado_id=entrada.turno_colocado_id,
        token_gestion=token_gestion,
    )


async def _resolver_entrada_por_token(
    session: AsyncSession,
    token: str,
) -> ListaEspera:
    fila_token = await resolver_token_gestion_recurso(
        session,
        token=token,
        recurso="lista_espera",
    )
    await marcar_usado(session, fila_token)
    entrada_id = uuid.UUID(fila_token.recurso_id)
    entrada = (
        await session.execute(
            select(ListaEspera).where(
                ListaEspera.id == entrada_id,
                ListaEspera.tenant_id == fila_token.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entrada is None:
        raise NoEncontrado("Che, no encontramos la solicitud asociada a ese link.")
    return entrada


@router.get("/lista-espera", response_model=list[ListaEsperaRead])
async def listar_lista_espera_endpoint(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LISTA_ESPERA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    estado: Annotated[EstadoListaEspera | None, Query()] = None,
    prestacion_id: Annotated[uuid.UUID | None, Query()] = None,
    profesional_id: Annotated[uuid.UUID | None, Query()] = None,
    paciente_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ListaEsperaRead]:
    stmt = select(ListaEspera).where(ListaEspera.tenant_id == actor.tenant_id)
    if estado is not None:
        stmt = stmt.where(ListaEspera.estado == estado.value)
    if prestacion_id is not None:
        stmt = stmt.where(ListaEspera.prestacion_id == prestacion_id)
    if profesional_id is not None:
        stmt = stmt.where(ListaEspera.profesional_id == profesional_id)
    if paciente_id is not None:
        stmt = stmt.where(ListaEspera.paciente_id == paciente_id)

    stmt = stmt.order_by(ListaEspera.prioridad.asc(), ListaEspera.created_at.asc())
    filas = (await session.execute(stmt)).scalars().all()
    return [_serializar_entrada(e) for e in filas]


@router.post(
    "/lista-espera",
    response_model=ListaEsperaRead,
    status_code=status.HTTP_201_CREATED,
)
async def crear_lista_espera_endpoint(
    payload: ListaEsperaCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LISTA_ESPERA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaRead:
    entrada, token = await crear_entrada_lista_espera(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=payload.paciente_id,
        prestacion_id=payload.prestacion_id,
        profesional_id=payload.profesional_id,
        prioridad=payload.prioridad,
        canal_aviso=payload.canal_aviso,
        observaciones=payload.observaciones,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return _serializar_entrada(entrada, token_gestion=token)


@router.get("/lista-espera/{entrada_id}", response_model=ListaEsperaRead)
async def obtener_lista_espera_endpoint(
    entrada_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LISTA_ESPERA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaRead:
    entrada = (
        await session.execute(
            select(ListaEspera).where(
                ListaEspera.id == entrada_id,
                ListaEspera.tenant_id == actor.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entrada is None:
        raise NoEncontrado("Che, no encontramos esa entrada en la lista de espera.")
    return _serializar_entrada(entrada)


@router.patch("/lista-espera/{entrada_id}", response_model=ListaEsperaRead)
async def actualizar_lista_espera_endpoint(
    entrada_id: uuid.UUID,
    payload: ListaEsperaUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LISTA_ESPERA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaRead:
    entrada = (
        await session.execute(
            select(ListaEspera).where(
                ListaEspera.id == entrada_id,
                ListaEspera.tenant_id == actor.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entrada is None:
        raise NoEncontrado("Che, no encontramos esa entrada en la lista de espera.")

    antes: dict[str, object] = {
        "prioridad": entrada.prioridad,
        "canal_aviso": entrada.canal_aviso,
        "estado": entrada.estado,
    }
    if payload.prioridad is not None:
        entrada.prioridad = payload.prioridad
    if payload.canal_aviso is not None:
        entrada.canal_aviso = payload.canal_aviso.value
    if payload.observaciones is not None:
        entrada.observaciones = payload.observaciones

    if payload.estado is not None:
        if payload.estado == EstadoListaEspera.BAJA:
            entrada = await dar_baja_lista_espera(
                session,
                tenant_id=actor.tenant_id,
                entrada_id=entrada.id,
                actor_id=actor.usuario_id,
            )
            await session.commit()
            return _serializar_entrada(entrada)
        if payload.estado == EstadoListaEspera.ACTIVA:
            entrada.estado = EstadoListaEspera.ACTIVA.value
        else:
            raise EntidadInvalida(
                "Desde este endpoint solo podés pasar la entrada a 'activa' o 'baja'."
            )

    await session.flush()
    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="lista_espera.actualizar",
        entidad="lista_espera",
        entidad_id=str(entrada.id),
        antes=antes,
        despues={
            "prioridad": entrada.prioridad,
            "canal_aviso": entrada.canal_aviso,
            "estado": entrada.estado,
        },
    )
    await session.commit()
    return _serializar_entrada(entrada)


@router.post("/lista-espera/ofrecer-hueco", response_model=ListaEsperaRead | None)
async def ofrecer_hueco_endpoint(
    payload: OfrecerHuecoRequest,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LISTA_ESPERA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaRead | None:
    avisada = await ofrecer_hueco_lista_espera(
        session,
        tenant_id=actor.tenant_id,
        prestacion_id=payload.prestacion_id,
        profesional_id=payload.profesional_id,
        sillon_id=payload.sillon_id,
        inicio=payload.inicio,
        fin=payload.fin,
        ventana_min=payload.ventana_min,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    if avisada is None:
        return None
    return _serializar_entrada(avisada)


@router_publico.post(
    "/reservar/{slug}/lista-espera",
    response_model=ListaEsperaPublicaRead,
    status_code=status.HTTP_201_CREATED,
)
async def anotarse_lista_espera_publica_endpoint(
    slug: str,
    payload: ListaEsperaPublicaCreate,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaPublicaRead:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == slug, Tenant.activo.is_(True)))
    ).scalar_one_or_none()
    if tenant is None:
        raise NoEncontrado("Che, no encontramos ese consultorio o no está activo.")

    paciente, _ = await get_or_create_paciente(
        session,
        tenant_id=tenant.id,
        nombre=payload.nombre,
        dni=payload.dni,
        telefono=payload.telefono,
        email=payload.email,
        fecha_nac=payload.fecha_nac,
        obra_social_id=payload.obra_social_id,
        nro_afiliado=payload.nro_afiliado,
        optin_wa=payload.optin_wa,
    )

    entrada, token = await crear_entrada_lista_espera(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        prestacion_id=payload.prestacion_id,
        profesional_id=payload.profesional_id,
        prioridad=1,
        canal_aviso=payload.canal_aviso,
        observaciones=payload.observaciones,
    )
    await session.commit()
    return await _armar_respuesta_publica_le(session, entrada, token_gestion=token)


@router_publico.get("/lista-espera/{token}", response_model=ListaEsperaPublicaRead)
async def ver_lista_espera_publica_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaPublicaRead:
    entrada = await _resolver_entrada_por_token(session, token)
    await session.commit()
    return await _armar_respuesta_publica_le(session, entrada)


@router_publico.post(
    "/lista-espera/{token}/aceptar",
    response_model=ListaEsperaPublicaRead,
    status_code=status.HTTP_201_CREATED,
)
async def aceptar_lista_espera_publica_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaPublicaRead:
    entrada = await _resolver_entrada_por_token(session, token)
    _, token_turno = await aceptar_oferta_lista_espera(
        session,
        tenant_id=entrada.tenant_id,
        entrada_id=entrada.id,
    )
    await session.commit()
    await session.refresh(entrada)
    return await _armar_respuesta_publica_le(session, entrada, token_gestion=token_turno)


@router_publico.post("/lista-espera/{token}/baja", response_model=ListaEsperaPublicaRead)
async def baja_lista_espera_publica_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ListaEsperaPublicaRead:
    entrada = await _resolver_entrada_por_token(session, token)
    entrada = await dar_baja_lista_espera(
        session,
        tenant_id=entrada.tenant_id,
        entrada_id=entrada.id,
    )
    await session.commit()
    return await _armar_respuesta_publica_le(session, entrada)
