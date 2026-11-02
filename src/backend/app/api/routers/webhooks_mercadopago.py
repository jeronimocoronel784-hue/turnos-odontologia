"""Webhook público de Mercado Pago y endpoints administrativos de cobros (C-12, US-031).

Cumple:
- RN-SE-04: toda notificación se autentica con HMAC-SHA256 (`x-signature`) antes de procesarse.
- RN-PA-03: idempotencia estricta por `mp_payment_id`; los reintentos responden `200`.
- RN-PA-05: las discrepancias quedan visibles para revisión manual (nunca auto-cierre).
- R1 / R4 / R8: schemas estrictos, `tenant_id` sólo del token y montos `Decimal`.
- El webhook no tiene tenant en el request: se deriva de la seña resuelta por
  `external_reference`, nunca del body.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_mercadopago import (
    CobroMPRead,
    DiscrepanciaMPRead,
    WebhookPayloadMP,
)
from app.api.security import ActorAutenticado, requiere
from app.application.mercadopago import (
    listar_cobros_mp,
    listar_discrepancias_mp,
    procesar_webhook_mp,
)
from app.domain.mercadopago import CobroMP, EstadoConciliacionMP, EstadoMP
from app.domain.rbac import Accion, Recurso
from app.infrastructure.mercadopago.client import verificar_firma_webhook_mp
from app.shared.exceptions import NoAutenticado
from app.shared.settings import Settings

router = APIRouter(tags=["mercadopago"])
router_webhook = APIRouter(tags=["webhooks-mercadopago"])


@router_webhook.post("/webhooks/mercadopago")
async def recibir_webhook_mercadopago_endpoint(
    request: Request,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
    x_signature: Annotated[str | None, Header(alias="x-signature")] = None,
    x_request_id: Annotated[str | None, Header(alias="x-request-id")] = None,
) -> dict[str, int]:
    """Recibe, autentica y procesa idempotentemente una notificación de Mercado Pago."""
    raw_body = await request.body()
    payload = WebhookPayloadMP.model_validate_json(raw_body)
    data_id = str(payload.data.get("id", ""))

    firma_valida = bool(settings.mp_webhook_secret) and verificar_firma_webhook_mp(
        x_signature=x_signature or "",
        request_id=x_request_id,
        data_id=data_id,
        secret=settings.mp_webhook_secret,
    )
    if not firma_valida:
        raise NoAutenticado("Che, la firma del webhook de Mercado Pago no es válida.")

    resultado = await procesar_webhook_mp(
        session,
        payload=payload.model_dump(),
        settings=settings,
    )
    await session.commit()

    procesado = resultado.cobro is not None and not resultado.duplicado and not resultado.ignorado
    return {
        "procesados": 1 if procesado else 0,
        "duplicados": 1 if resultado.duplicado else 0,
        "discrepancias": 1 if resultado.discrepancia else 0,
        "ignorados": 1 if resultado.ignorado else 0,
    }


# `Recurso.CAJA` + `Accion.ACTUALIZAR`: la conciliación de cobros es operación de caja
# (Dueño y Recepción), no lectura clínica; el Odontólogo recibe `403`.
_GUARD_CAJA_MP = requiere(Recurso.CAJA, Accion.ACTUALIZAR)


def _serializar_cobro(cobro: CobroMP) -> CobroMPRead:
    lectura = CobroMPRead.model_validate(cobro)
    return lectura.model_copy(update={"monto": Decimal(str(lectura.monto))})


@router.get("/pagos/mercadopago/cobros", response_model=list[CobroMPRead])
async def listar_cobros_mp_endpoint(
    actor: Annotated[ActorAutenticado, Depends(_GUARD_CAJA_MP)],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    sena_id: Annotated[uuid.UUID | None, Query()] = None,
    turno_id: Annotated[uuid.UUID | None, Query()] = None,
    estado_mp: Annotated[EstadoMP | None, Query()] = None,
    estado_conciliacion: Annotated[EstadoConciliacionMP | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CobroMPRead]:
    """Lista los cobros de Mercado Pago del consultorio con filtros básicos (R4)."""
    cobros = await listar_cobros_mp(
        session,
        tenant_id=actor.tenant_id,
        sena_id=sena_id,
        turno_id=turno_id,
        estado_mp=estado_mp,
        estado_conciliacion=estado_conciliacion,
        limite=limite,
        offset=offset,
    )
    return [_serializar_cobro(c) for c in cobros]


@router.get("/pagos/mercadopago/discrepancias", response_model=list[DiscrepanciaMPRead])
async def listar_discrepancias_mp_endpoint(
    actor: Annotated[ActorAutenticado, Depends(_GUARD_CAJA_MP)],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    sena_id: Annotated[uuid.UUID | None, Query()] = None,
    turno_id: Annotated[uuid.UUID | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DiscrepanciaMPRead]:
    """Lista los cobros en `discrepancia` con su motivo para resolución manual (RN-PA-05)."""
    filas = await listar_discrepancias_mp(
        session,
        tenant_id=actor.tenant_id,
        sena_id=sena_id,
        turno_id=turno_id,
        limite=limite,
        offset=offset,
    )
    return [
        DiscrepanciaMPRead(
            id=cobro.id,
            mp_payment_id=cobro.mp_payment_id,
            monto=Decimal(str(cobro.monto)),
            estado_mp=cobro.estado_mp,
            sena_id=cobro.sena_id,
            turno_id=cobro.turno_id,
            motivo=motivo,
            created_at=cobro.created_at,
        )
        for cobro, motivo in filas
    ]
