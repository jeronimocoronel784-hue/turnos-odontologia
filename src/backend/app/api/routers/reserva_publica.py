"""Router público de Reserva Online 24/7 y Autogestión por Token Opaco (C-06, Flujo 1, RN-SE-03).

Rutas sin sesión de usuario:
- `GET /reservar/{slug}`: catálogo público y slots reales disponibles.
- `POST /reservar/{slug}`: alta/actualización de paciente, turno `pendiente` y `token_gestion`.
- `GET /mis-turnos/{token}`: consulta del turno propio.
- `POST /mis-turnos/{token}/confirmar`: confirmación idempotente (exige seña paga, RN-PA-01).
- `POST /mis-turnos/{token}/cancelar`: cancelación respetando anticipación mínima (RN-AG-05).
- `POST /mis-turnos/{token}/reprogramar`: reprogramación 1-clic con nuevo token (RN-AG-06).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_agenda import (
    CancelarPublicoRequest,
    ReprogramarPublicoRequest,
    ReservaPublicaCreate,
    ReservaPublicaRead,
)
from app.api.schemas_mercadopago import PreferenciaRead
from app.application.agenda import (
    HORA_APERTURA_DEFAULT,
    HORA_CIERRE_DEFAULT,
    calcular_slots_disponibles,
    cambiar_estado_turno,
    cancelar_turno_publico,
    crear_turno,
    reprogramar_turno,
)
from app.application.caja import obtener_sena_por_turno
from app.application.mercadopago import crear_preferencia_para_sena
from app.application.pacientes import get_or_create_paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.tokens_publicos import (
    marcar_usado,
    resolver_token_gestion_recurso,
)
from app.shared.exceptions import NoEncontrado
from app.shared.settings import Settings

router = APIRouter(tags=["reserva-publica"])

# Tope de franjas devueltas al paciente: evita payloads enormes cuando hay varios
# profesionales y sillones (el cálculo sin filtros es un producto N x M).
LIMITE_SLOTS_PUBLICOS = 60


async def _obtener_tenant_por_slug(session: AsyncSession, slug: str) -> Tenant:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == slug, Tenant.activo.is_(True)))
    ).scalar_one_or_none()
    if tenant is None:
        raise NoEncontrado("Che, no encontramos ese consultorio o no está activo.")
    return tenant


async def _armar_respuesta_publica(
    session: AsyncSession,
    turno: Turno,
    *,
    token_gestion: str | None = None,
) -> ReservaPublicaRead:
    prestacion = await session.get(Prestacion, turno.prestacion_id)
    profesional = await session.get(Usuario, turno.profesional_id)
    sillon = await session.get(Sillon, turno.sillon_id)
    return ReservaPublicaRead(
        turno_id=turno.id,
        estado=EstadoTurno(turno.estado),
        inicio=turno.inicio,
        fin=turno.fin,
        prestacion_id=turno.prestacion_id,
        prestacion_nombre=prestacion.nombre if prestacion else "",
        profesional_id=turno.profesional_id,
        profesional_nombre=profesional.nombre if profesional else "",
        sillon_id=turno.sillon_id,
        sillon_nombre=sillon.nombre if sillon else "",
        requiere_sena=bool(prestacion.requiere_sena) if prestacion else False,
        monto_sena=prestacion.monto_sena if prestacion else None,
        sena_cobrada=turno.sena_cobrada,
        token_gestion=token_gestion,
    )


async def _resolver_turno_por_token(session: AsyncSession, token: str) -> tuple[Turno, Tenant]:
    fila_token = await resolver_token_gestion_recurso(session, token=token, recurso="turno")
    await marcar_usado(session, fila_token)
    turno_id = uuid.UUID(fila_token.recurso_id)
    turno = (
        await session.execute(
            select(Turno).where(
                Turno.id == turno_id,
                Turno.tenant_id == fila_token.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if turno is None:
        raise NoEncontrado("Che, no encontramos el turno asociado a ese link.")
    tenant = await session.get(Tenant, fila_token.tenant_id)
    if tenant is None:
        raise NoEncontrado("Che, el consultorio ya no está activo.")
    return turno, tenant


@router.get("/reservar/{slug}")
async def disponibilidad_publica_endpoint(
    slug: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    prestacion_id: Annotated[uuid.UUID | None, Query()] = None,
    profesional_id: Annotated[uuid.UUID | None, Query()] = None,
    sillon_id: Annotated[uuid.UUID | None, Query()] = None,
    fecha: Annotated[date | None, Query()] = None,
) -> dict[str, Any]:
    tenant = await _obtener_tenant_por_slug(session, slug)

    prestaciones = (
        (
            await session.execute(
                select(Prestacion)
                .where(Prestacion.tenant_id == tenant.id, Prestacion.activa.is_(True))
                .order_by(Prestacion.nombre)
            )
        )
        .scalars()
        .all()
    )

    profesionales = (
        (
            await session.execute(
                select(Usuario)
                .where(
                    Usuario.tenant_id == tenant.id,
                    Usuario.activo.is_(True),
                    Usuario.rol.in_([RolUsuario.ODONTOLOGO.value, RolUsuario.DUENO.value]),
                )
                .order_by(Usuario.nombre)
            )
        )
        .scalars()
        .all()
    )

    sillones = (
        (
            await session.execute(
                select(Sillon)
                .where(Sillon.tenant_id == tenant.id, Sillon.activo.is_(True))
                .order_by(Sillon.nombre)
            )
        )
        .scalars()
        .all()
    )

    slots_disponibles: list[dict[str, str]] = []
    if prestacion_id:
        prest_sel = next((p for p in prestaciones if p.id == prestacion_id), None)
        if prest_sel is not None:
            dia_base = fecha or (datetime.now(UTC) + timedelta(days=1)).date()
            desde = datetime.combine(dia_base, time(HORA_APERTURA_DEFAULT, 0), tzinfo=UTC)
            hasta = datetime.combine(dia_base, time(HORA_CIERRE_DEFAULT, 0), tzinfo=UTC)
            # El paciente puede filtrar por profesional y/o sillón; sin filtro se calcula
            # el producto profesional x sillón para no esconder disponibilidad real.
            profesionales_objetivo = (
                [p for p in profesionales if p.id == profesional_id]
                if profesional_id
                else list(profesionales)
            )
            sillones_objetivo = (
                [s for s in sillones if s.id == sillon_id] if sillon_id else list(sillones)
            )
            vistos: set[tuple[str, str, str]] = set()
            for profesional in profesionales_objetivo:
                for sillon in sillones_objetivo:
                    for slot in await calcular_slots_disponibles(
                        session,
                        tenant_id=tenant.id,
                        profesional_id=profesional.id,
                        sillon_id=sillon.id,
                        duracion_min=prest_sel.duracion_min,
                        desde=desde,
                        hasta=hasta,
                    ):
                        clave = (slot["inicio"], slot["profesional_id"], slot["sillon_id"])
                        if clave not in vistos:
                            vistos.add(clave)
                            slots_disponibles.append(slot)
            slots_disponibles.sort(key=lambda s: (s["inicio"], s["profesional_id"]))
            slots_disponibles = slots_disponibles[:LIMITE_SLOTS_PUBLICOS]

    return {
        "tenant_slug": tenant.slug,
        "tenant_nombre": tenant.nombre,
        "prestaciones": [
            {
                "id": str(p.id),
                "nombre": p.nombre,
                "duracion_min": p.duracion_min,
                "precio_particular": str(p.precio_particular),
                "requiere_sena": p.requiere_sena,
                "monto_sena": str(p.monto_sena) if p.monto_sena is not None else None,
            }
            for p in prestaciones
        ],
        "profesionales": [
            {"id": str(u.id), "nombre": u.nombre, "matricula": u.matricula} for u in profesionales
        ],
        "sillones": [
            {"id": str(s.id), "nombre": s.nombre, "sucursal": s.sucursal} for s in sillones
        ],
        "slots_disponibles": slots_disponibles,
    }


@router.post(
    "/reservar/{slug}",
    response_model=ReservaPublicaRead,
    status_code=status.HTTP_201_CREATED,
)
async def crear_reserva_publica_endpoint(
    slug: str,
    payload: ReservaPublicaCreate,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ReservaPublicaRead:
    tenant = await _obtener_tenant_por_slug(session, slug)

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

    turno, token = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=payload.profesional_id,
        sillon_id=payload.sillon_id,
        prestacion_id=payload.prestacion_id,
        inicio=payload.inicio,
        origen=OrigenTurno.ONLINE,
        sobreturno=False,
        actor_id=None,
    )
    await session.commit()
    return await _armar_respuesta_publica(session, turno, token_gestion=token)


@router.get("/mis-turnos/{token}", response_model=ReservaPublicaRead)
async def ver_mi_turno_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ReservaPublicaRead:
    turno, _ = await _resolver_turno_por_token(session, token)
    await session.commit()
    return await _armar_respuesta_publica(session, turno)


@router.post("/mis-turnos/{token}/confirmar", response_model=ReservaPublicaRead)
async def confirmar_mi_turno_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ReservaPublicaRead:
    turno, tenant = await _resolver_turno_por_token(session, token)
    turno = await cambiar_estado_turno(
        session,
        tenant_id=tenant.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.CONFIRMADO,
        idempotente=True,
    )
    await session.commit()
    return await _armar_respuesta_publica(session, turno)


@router.get("/mis-turnos/{token}/disponibilidad")
async def disponibilidad_mi_turno_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    fecha: Annotated[date | None, Query()] = None,
) -> list[dict[str, str]]:
    """Franjas libres para reprogramar el turno propio con el mismo profesional y sillón.

    Se resuelve por token (RN-SE-03): el paciente no necesita conocer el slug del
    consultorio y sólo ve disponibilidad del recurso que ya tiene reservado.
    """
    turno, tenant = await _resolver_turno_por_token(session, token)
    prestacion = await session.get(Prestacion, turno.prestacion_id)
    if prestacion is None:
        raise NoEncontrado("Che, no encontramos la prestación de este turno.")

    dia_base = fecha or (datetime.now(UTC) + timedelta(days=1)).date()
    desde = datetime.combine(dia_base, time(HORA_APERTURA_DEFAULT, 0), tzinfo=UTC)
    hasta = datetime.combine(dia_base, time(HORA_CIERRE_DEFAULT, 0), tzinfo=UTC)
    slots = await calcular_slots_disponibles(
        session,
        tenant_id=tenant.id,
        profesional_id=turno.profesional_id,
        sillon_id=turno.sillon_id,
        duracion_min=prestacion.duracion_min,
        desde=desde,
        hasta=hasta,
    )
    await session.commit()
    return slots


@router.post("/mis-turnos/{token}/pago", response_model=PreferenciaRead)
async def generar_pago_mi_turno_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
) -> PreferenciaRead:
    """Genera la preferencia de Mercado Pago de la seña pendiente del turno (RN-PA-02).

    El monto y el vencimiento salen siempre de la seña persistida: el paciente nunca
    envía montos (R8). Un turno sin seña o con la seña ya resuelta responde 404/409.
    """
    turno, tenant = await _resolver_turno_por_token(session, token)
    sena = await obtener_sena_por_turno(session, tenant_id=tenant.id, turno_id=turno.id)
    if sena is None:
        raise NoEncontrado("Che, este turno no tiene una seña pendiente de pago.")
    preferencia = await crear_preferencia_para_sena(
        session,
        tenant_id=tenant.id,
        sena_id=sena.id,
        settings=settings,
    )
    await session.commit()
    return preferencia


@router.post("/mis-turnos/{token}/cancelar", response_model=ReservaPublicaRead)
async def cancelar_mi_turno_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    payload: CancelarPublicoRequest | None = None,
) -> ReservaPublicaRead:
    turno, tenant = await _resolver_turno_por_token(session, token)
    motivo = payload.motivo if payload else None
    turno = await cancelar_turno_publico(
        session,
        tenant_id=tenant.id,
        turno_id=turno.id,
        motivo=motivo,
    )
    await session.commit()
    return await _armar_respuesta_publica(session, turno)


@router.post(
    "/mis-turnos/{token}/reprogramar",
    response_model=ReservaPublicaRead,
    status_code=status.HTTP_201_CREATED,
)
async def reprogramar_mi_turno_endpoint(
    token: str,
    payload: ReprogramarPublicoRequest,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ReservaPublicaRead:
    turno, tenant = await _resolver_turno_por_token(session, token)
    nuevo_turno, nuevo_token = await reprogramar_turno(
        session,
        tenant_id=tenant.id,
        turno_id=turno.id,
        nuevo_inicio=payload.nuevo_inicio,
        motivo=payload.motivo,
        validar_anticipacion=True,
    )
    await session.commit()
    return await _armar_respuesta_publica(session, nuevo_turno, token_gestion=nuevo_token)
