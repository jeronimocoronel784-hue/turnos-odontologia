"""Casos de uso de Lista de Espera y Oferta Proactiva de Huecos (C-07, Flujo 6).

Reglas implementadas:
- RN-LE-01: orden por `(prioridad ASC, created_at ASC)`, un aviso vigente por hueco con ventana.
- RN-LE-02: idempotencia por `(entrada, hueco)` mediante `generar_idempotency_key_hueco` y rotación
  al siguiente candidato cuando la ventana de respuesta expira.
- RN-LE-03: colocación crea `Turno` vinculado (`crear_turno`), marca la entrada `colocada` y
  protege contra doble aceptación simultánea (`ConflictoDisponibilidad` 409 con alternativas).
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auditoria import registrar_auditoria
from app.domain.lista_espera import (
    CanalAviso,
    EstadoListaEspera,
    ListaEspera,
    generar_idempotency_key_hueco,
)
from app.domain.mixins import asegurar_utc
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.turno import OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.tokens_publicos import crear_token_gestion
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

DIAS_VENCIMIENTO_TOKEN_LISTA_ESPERA = 30
VENTANA_OFERTA_MIN_DEFAULT = 60


async def crear_entrada_lista_espera(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    profesional_id: uuid.UUID | None = None,
    prioridad: int = 1,
    canal_aviso: CanalAviso = CanalAviso.WA,
    observaciones: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> tuple[ListaEspera, str]:
    """Crea una entrada activa en la lista de espera y emite su TokenGestion opaco."""
    if prioridad < 0:
        raise EntidadInvalida("La prioridad de la lista de espera no puede ser negativa.")

    paciente = (
        await session.execute(
            select(Paciente).where(
                Paciente.id == paciente_id,
                Paciente.tenant_id == tenant_id,
                Paciente.activo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos ese paciente activo en el consultorio.")

    prestacion = (
        await session.execute(
            select(Prestacion).where(
                Prestacion.id == prestacion_id,
                Prestacion.tenant_id == tenant_id,
                Prestacion.activa.is_(True),
            )
        )
    ).scalar_one_or_none()
    if prestacion is None:
        raise NoEncontrado("Che, esa prestación no existe o está inactiva en el consultorio.")

    if profesional_id is not None:
        prof = (
            await session.execute(
                select(Usuario).where(
                    Usuario.id == profesional_id,
                    Usuario.tenant_id == tenant_id,
                    Usuario.activo.is_(True),
                )
            )
        ).scalar_one_or_none()
        if prof is None or prof.rol not in (
            RolUsuario.ODONTOLOGO.value,
            RolUsuario.DUENO.value,
        ):
            raise EntidadInvalida(
                "El profesional elegido no existe, está inactivo o no atiende consultorio."
            )

    obs_limpia = observaciones.strip() if observaciones else None
    entrada = ListaEspera(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        prestacion_id=prestacion_id,
        profesional_id=profesional_id,
        prioridad=prioridad,
        estado=EstadoListaEspera.ACTIVA.value,
        canal_aviso=canal_aviso.value,
        observaciones=obs_limpia,
        avisos_keys=[],
    )
    session.add(entrada)
    await session.flush()

    token = await crear_token_gestion(
        session,
        tenant_id=tenant_id,
        recurso="lista_espera",
        recurso_id=str(entrada.id),
        vence_at=datetime.now(UTC) + timedelta(days=DIAS_VENCIMIENTO_TOKEN_LISTA_ESPERA),
    )

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="lista_espera.crear",
        entidad="lista_espera",
        entidad_id=str(entrada.id),
        despues={
            "estado": entrada.estado,
            "prioridad": entrada.prioridad,
            "prestacion_id": str(entrada.prestacion_id),
            "profesional_id": str(entrada.profesional_id) if entrada.profesional_id else None,
            "canal_aviso": entrada.canal_aviso,
        },
    )
    return entrada, token


async def ofrecer_hueco_lista_espera(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    profesional_id: uuid.UUID,
    sillon_id: uuid.UUID,
    inicio: datetime,
    fin: datetime,
    ventana_min: int = VENTANA_OFERTA_MIN_DEFAULT,
    ahora: datetime | None = None,
    actor_id: uuid.UUID | None = None,
) -> ListaEspera | None:
    """Ofrece el hueco liberado al primer candidato compatible por (prioridad, created_at).

    - Si ya existe una entrada `avisada` para ese mismo hueco y su ventana sigue vigente,
      la devuelve de forma idempotente (RN-LE-02).
    - Si una entrada `avisada` tiene su ventana vencida (`aviso_vence_at <= ahora`),
      la devuelve a `activa` y selecciona la siguiente entrada que no haya recibido
      aún un aviso para este hueco (RN-LE-01, RN-LE-02).
    """
    inicio_utc = asegurar_utc(inicio)
    fin_utc = asegurar_utc(fin)
    ahora_utc = asegurar_utc(ahora) if ahora is not None else datetime.now(UTC)

    candidatos = (
        (
            await session.execute(
                select(ListaEspera)
                .where(
                    ListaEspera.tenant_id == tenant_id,
                    ListaEspera.prestacion_id == prestacion_id,
                    ListaEspera.estado.in_(
                        [EstadoListaEspera.ACTIVA.value, EstadoListaEspera.AVISADA.value]
                    ),
                    or_(
                        ListaEspera.profesional_id.is_(None),
                        ListaEspera.profesional_id == profesional_id,
                    ),
                )
                .order_by(ListaEspera.prioridad.asc(), ListaEspera.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    # 1. Revisar entradas en estado AVISADA: si es el mismo hueco y sigue vigente -> idempotente;
    #    si su ventana ya venció -> devolver a ACTIVA para destrabar la cola.
    for cand in candidatos:
        if cand.estado != EstadoListaEspera.AVISADA.value:
            continue
        key_cand = generar_idempotency_key_hueco(
            entrada_id=cand.id,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            inicio=inicio_utc,
        )
        vence_cand = asegurar_utc(cand.aviso_vence_at) if cand.aviso_vence_at else None
        if vence_cand is not None and vence_cand <= ahora_utc:
            cand.estado = EstadoListaEspera.ACTIVA.value
            cand.hueco_inicio = None
            cand.hueco_fin = None
            cand.hueco_profesional_id = None
            cand.hueco_sillon_id = None
            cand.aviso_vence_at = None
        elif cand.ultimo_idempotency_key == key_cand:
            return cand

    await session.flush()

    # 2. Elegir la primera entrada ACTIVA que no haya sido avisada para este mismo hueco
    for cand in candidatos:
        if cand.estado != EstadoListaEspera.ACTIVA.value:
            continue
        key_cand = generar_idempotency_key_hueco(
            entrada_id=cand.id,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            inicio=inicio_utc,
        )
        historial_keys = list(cand.avisos_keys or [])
        if key_cand in historial_keys or cand.ultimo_idempotency_key == key_cand:
            continue

        cand.estado = EstadoListaEspera.AVISADA.value
        cand.hueco_inicio = inicio_utc
        cand.hueco_fin = fin_utc
        cand.hueco_profesional_id = profesional_id
        cand.hueco_sillon_id = sillon_id
        cand.aviso_vence_at = ahora_utc + timedelta(minutes=ventana_min)
        cand.ultimo_idempotency_key = key_cand
        historial_keys.append(key_cand)
        cand.avisos_keys = historial_keys
        await session.flush()

        await registrar_auditoria(
            session,
            tenant_id=tenant_id,
            actor_id=actor_id,
            accion="lista_espera.avisar",
            entidad="lista_espera",
            entidad_id=str(cand.id),
            despues={
                "estado": cand.estado,
                "hueco_inicio": inicio_utc.isoformat(),
                "hueco_fin": fin_utc.isoformat(),
                "profesional_id": str(profesional_id),
                "sillon_id": str(sillon_id),
                "idempotency_key": key_cand,
                "aviso_vence_at": cand.aviso_vence_at.isoformat(),
            },
        )
        return cand

    return None


async def aceptar_oferta_lista_espera(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entrada_id: uuid.UUID,
    ahora: datetime | None = None,
    actor_id: uuid.UUID | None = None,
) -> tuple[Turno, str]:
    """Acepta el hueco ofrecido, crea el Turno y marca la entrada `colocada` (RN-LE-03)."""
    from app.application.agenda import crear_turno

    entrada = (
        await session.execute(
            select(ListaEspera).where(
                ListaEspera.id == entrada_id,
                ListaEspera.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entrada is None:
        raise NoEncontrado("Che, no encontramos esa entrada en la lista de espera.")

    if entrada.estado != EstadoListaEspera.AVISADA.value or entrada.hueco_inicio is None:
        raise Conflicto("Che, esta solicitud no tiene un hueco activo pendiente de aceptación.")

    ahora_utc = asegurar_utc(ahora) if ahora is not None else datetime.now(UTC)
    if entrada.aviso_vence_at is not None and asegurar_utc(entrada.aviso_vence_at) <= ahora_utc:
        # Si venció, rotar al siguiente candidato antes de rechazar
        if (
            entrada.hueco_profesional_id is not None
            and entrada.hueco_sillon_id is not None
            and entrada.hueco_fin is not None
        ):
            await ofrecer_hueco_lista_espera(
                session,
                tenant_id=tenant_id,
                prestacion_id=entrada.prestacion_id,
                profesional_id=entrada.hueco_profesional_id,
                sillon_id=entrada.hueco_sillon_id,
                inicio=entrada.hueco_inicio,
                fin=entrada.hueco_fin,
                ahora=ahora_utc,
            )
        raise Conflicto(
            "Che, venció el tiempo para aceptar este horario. "
            "Seguís activo en la lista de espera para el próximo hueco disponible."
        )

    if entrada.hueco_profesional_id is None or entrada.hueco_sillon_id is None:
        raise Conflicto("Che, el hueco ofrecido está incompleto.")

    turno, token_turno = await crear_turno(
        session,
        tenant_id=tenant_id,
        paciente_id=entrada.paciente_id,
        profesional_id=entrada.hueco_profesional_id,
        sillon_id=entrada.hueco_sillon_id,
        prestacion_id=entrada.prestacion_id,
        inicio=entrada.hueco_inicio,
        fin=entrada.hueco_fin,
        origen=OrigenTurno.ONLINE,
        sobreturno=False,
        observaciones=entrada.observaciones,
        actor_id=actor_id,
    )

    entrada.estado = EstadoListaEspera.COLOCADA.value
    entrada.turno_colocado_id = turno.id
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="lista_espera.colocar",
        entidad="lista_espera",
        entidad_id=str(entrada.id),
        antes={"estado": EstadoListaEspera.AVISADA.value},
        despues={
            "estado": entrada.estado,
            "turno_colocado_id": str(turno.id),
        },
    )
    return turno, token_turno


async def dar_baja_lista_espera(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entrada_id: uuid.UUID,
    ahora: datetime | None = None,
    actor_id: uuid.UUID | None = None,
) -> ListaEspera:
    """Da de baja una entrada; si estaba `avisada`, rota el hueco al siguiente candidato."""
    entrada = (
        await session.execute(
            select(ListaEspera).where(
                ListaEspera.id == entrada_id,
                ListaEspera.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entrada is None:
        raise NoEncontrado("Che, no encontramos esa entrada en la lista de espera.")

    if entrada.estado == EstadoListaEspera.BAJA.value:
        return entrada

    estaba_avisada = entrada.estado == EstadoListaEspera.AVISADA.value
    hueco_ini = entrada.hueco_inicio
    hueco_fin = entrada.hueco_fin
    hueco_prof = entrada.hueco_profesional_id
    hueco_sillon = entrada.hueco_sillon_id

    estado_anterior = entrada.estado
    entrada.estado = EstadoListaEspera.BAJA.value
    entrada.hueco_inicio = None
    entrada.hueco_fin = None
    entrada.hueco_profesional_id = None
    entrada.hueco_sillon_id = None
    entrada.aviso_vence_at = None
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="lista_espera.baja",
        entidad="lista_espera",
        entidad_id=str(entrada.id),
        antes={"estado": estado_anterior},
        despues={"estado": entrada.estado},
    )

    if (
        estaba_avisada
        and hueco_ini is not None
        and hueco_fin is not None
        and hueco_prof is not None
        and hueco_sillon is not None
    ):
        await ofrecer_hueco_lista_espera(
            session,
            tenant_id=tenant_id,
            prestacion_id=entrada.prestacion_id,
            profesional_id=hueco_prof,
            sillon_id=hueco_sillon,
            inicio=hueco_ini,
            fin=hueco_fin,
            ahora=ahora,
            actor_id=actor_id,
        )

    return entrada
