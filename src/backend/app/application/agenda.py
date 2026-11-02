"""Casos de uso de Agenda, Turnos, Bloqueos y Reserva Pública (C-06).

Reglas implementadas:
- RN-AG-01: anti-solapamiento por profesional y por sillón salvo sobreturno explícito.
- RN-AG-02: fin = inicio + duracion_prestacion salvo override explícito auditado.
- RN-AG-03: bloqueos horarios no son reservables por ningún canal (ni con sobreturno).
- RN-AG-04: sobreturno exige flag explícito + motivo en observaciones y queda auditado.
- RN-AG-05: cancelación/reprogramación pública exige anticipación mínima (cancelacion_hs).
- RN-AG-06: reprogramar pasa el turno original a reprogramado y crea uno nuevo con turno_origen_id.
- RN-AG-07: grafo cerrado de estados del turno.
- RN-AG-08: confirmación idempotente por token/WA.
- RN-PA-01: turno cuya prestación exige seña impaga no puede pasar a confirmado.
- RN-GL-02: rechazos 409 devuelven mensaje rioplatense y slots alternativos disponibles.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auditoria import registrar_auditoria
from app.domain.bloqueo import Bloqueo, MotivoBloqueo
from app.domain.mixins import asegurar_utc
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import (
    ESTADOS_ACTIVOS_AGENDA,
    EstadoTurno,
    OrigenTurno,
    Turno,
    calcular_fin_turno,
    es_transicion_valida,
)
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.tokens_publicos import crear_token_gestion
from app.shared.exceptions import (
    Conflicto,
    ConflictoDisponibilidad,
    EntidadInvalida,
    NoEncontrado,
)

HORA_APERTURA_DEFAULT = 8
HORA_CIERRE_DEFAULT = 18
DIAS_VENCIMIENTO_TOKEN_TURNO = 7


def _rango_se_solapa(
    inicio_a: datetime, fin_a: datetime, inicio_b: datetime, fin_b: datetime
) -> bool:
    """True si los intervalos semiabiertos [inicio_a, fin_a) e [inicio_b, fin_b) se superponen."""
    return asegurar_utc(inicio_a) < asegurar_utc(fin_b) and asegurar_utc(fin_a) > asegurar_utc(
        inicio_b
    )


async def obtener_entidades_turno(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    sillon_id: uuid.UUID,
    prestacion_id: uuid.UUID,
) -> tuple[Paciente, Usuario, Sillon, Prestacion]:
    """Carga y valida que paciente, profesional, sillón y prestación estén activos en el tenant."""
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

    profesional = (
        await session.execute(
            select(Usuario).where(
                Usuario.id == profesional_id,
                Usuario.tenant_id == tenant_id,
                Usuario.activo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if profesional is None or profesional.rol not in (
        RolUsuario.ODONTOLOGO.value,
        RolUsuario.DUENO.value,
    ):
        raise EntidadInvalida(
            "El profesional elegido no existe, está inactivo o no atiende consultorio."
        )

    sillon = (
        await session.execute(
            select(Sillon).where(
                Sillon.id == sillon_id,
                Sillon.tenant_id == tenant_id,
                Sillon.activo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if sillon is None:
        raise NoEncontrado("Che, ese sillón no existe o está inactivo en el consultorio.")

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

    return paciente, profesional, sillon, prestacion


async def calcular_slots_disponibles(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    profesional_id: uuid.UUID,
    sillon_id: uuid.UUID,
    duracion_min: int,
    desde: datetime,
    hasta: datetime,
    limite: int = 20,
) -> list[dict[str, str]]:
    """Calcula slots libres reales de `duracion_min` descontando turnos activos y bloqueos."""
    desde_utc = asegurar_utc(desde)
    hasta_utc = asegurar_utc(hasta)
    if hasta_utc <= desde_utc or duracion_min <= 0:
        return []

    estados_activos = [e.value for e in ESTADOS_ACTIVOS_AGENDA]
    turnos = (
        (
            await session.execute(
                select(Turno).where(
                    Turno.tenant_id == tenant_id,
                    Turno.estado.in_(estados_activos),
                    or_(Turno.profesional_id == profesional_id, Turno.sillon_id == sillon_id),
                    Turno.inicio < hasta_utc,
                    Turno.fin > desde_utc,
                )
            )
        )
        .scalars()
        .all()
    )

    bloqueos = (
        (
            await session.execute(
                select(Bloqueo).where(
                    Bloqueo.tenant_id == tenant_id,
                    or_(Bloqueo.profesional_id == profesional_id, Bloqueo.sillon_id == sillon_id),
                    Bloqueo.desde < hasta_utc,
                    Bloqueo.hasta > desde_utc,
                )
            )
        )
        .scalars()
        .all()
    )

    ocupados: list[tuple[datetime, datetime]] = [
        (asegurar_utc(t.inicio), asegurar_utc(t.fin)) for t in turnos
    ] + [(asegurar_utc(b.desde), asegurar_utc(b.hasta)) for b in bloqueos]

    slots: list[dict[str, str]] = []
    paso = timedelta(minutes=duracion_min)
    dia_cursor = desde_utc.date()
    dia_fin = hasta_utc.date()

    while dia_cursor <= dia_fin and len(slots) < limite:
        apertura = datetime.combine(dia_cursor, time(HORA_APERTURA_DEFAULT, 0), tzinfo=UTC)
        cierre = datetime.combine(dia_cursor, time(HORA_CIERRE_DEFAULT, 0), tzinfo=UTC)
        cursor = max(apertura, desde_utc)
        limite_dia = min(cierre, hasta_utc)

        while cursor + paso <= limite_dia and len(slots) < limite:
            fin_slot = cursor + paso
            hay_choque = any(
                _rango_se_solapa(cursor, fin_slot, ini_oc, fin_oc) for ini_oc, fin_oc in ocupados
            )
            if not hay_choque:
                slots.append(
                    {
                        "inicio": cursor.isoformat(),
                        "fin": fin_slot.isoformat(),
                        "profesional_id": str(profesional_id),
                        "sillon_id": str(sillon_id),
                    }
                )
            cursor += paso
        dia_cursor += timedelta(days=1)

    return slots


async def verificar_disponibilidad(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    profesional_id: uuid.UUID,
    sillon_id: uuid.UUID,
    inicio: datetime,
    fin: datetime,
    duracion_min: int,
    sobreturno: bool = False,
    excluir_turno_id: uuid.UUID | None = None,
) -> None:
    """Verifica que [inicio, fin) no choque con bloqueos (RN-AG-03) ni turnos (RN-AG-01)."""
    inicio_utc = asegurar_utc(inicio)
    fin_utc = asegurar_utc(fin)

    # 1. Bloqueos horarios: ningún turno (ni sobreturno) puede pisar un bloqueo (RN-AG-03)
    bloqueos = (
        (
            await session.execute(
                select(Bloqueo).where(
                    Bloqueo.tenant_id == tenant_id,
                    or_(Bloqueo.profesional_id == profesional_id, Bloqueo.sillon_id == sillon_id),
                    Bloqueo.desde < fin_utc,
                    Bloqueo.hasta > inicio_utc,
                )
            )
        )
        .scalars()
        .all()
    )

    if bloqueos:
        alternativas = await calcular_slots_disponibles(
            session,
            tenant_id=tenant_id,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            duracion_min=duracion_min,
            desde=datetime.combine(inicio_utc.date(), time(HORA_APERTURA_DEFAULT, 0), tzinfo=UTC),
            hasta=inicio_utc + timedelta(days=3),
            limite=5,
        )
        raise ConflictoDisponibilidad(
            "Che, ese horario está bloqueado en la agenda. "
            "Elegí alguno de los horarios alternativos disponibles.",
            slots_alternativos=alternativas,
        )

    if sobreturno:
        return

    # 2. Solapamiento de turnos activos por profesional o por sillón (RN-AG-01)
    estados_activos = [e.value for e in ESTADOS_ACTIVOS_AGENDA]
    stmt = select(Turno).where(
        Turno.tenant_id == tenant_id,
        Turno.estado.in_(estados_activos),
        or_(Turno.profesional_id == profesional_id, Turno.sillon_id == sillon_id),
        Turno.inicio < fin_utc,
        Turno.fin > inicio_utc,
    )
    if excluir_turno_id is not None:
        stmt = stmt.where(Turno.id != excluir_turno_id)

    choques = (await session.execute(stmt)).scalars().all()
    if choques:
        alternativas = await calcular_slots_disponibles(
            session,
            tenant_id=tenant_id,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            duracion_min=duracion_min,
            desde=datetime.combine(inicio_utc.date(), time(HORA_APERTURA_DEFAULT, 0), tzinfo=UTC),
            hasta=inicio_utc + timedelta(days=3),
            limite=5,
        )
        raise ConflictoDisponibilidad(
            "Che, ese horario ya está ocupado para el profesional o el sillón. "
            "Te dejamos horarios alternativos libres.",
            slots_alternativos=alternativas,
        )


async def crear_turno(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    profesional_id: uuid.UUID,
    sillon_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    inicio: datetime,
    fin: datetime | None = None,
    origen: OrigenTurno = OrigenTurno.PRESENCIAL,
    sobreturno: bool = False,
    observaciones: str | None = None,
    sena_cobrada: bool = False,
    turno_origen_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> tuple[Turno, str]:
    """Crea un turno validando disponibilidad, duración y sobreturno, y emite su TokenGestion."""
    _, _, _, prestacion = await obtener_entidades_turno(
        session,
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        profesional_id=profesional_id,
        sillon_id=sillon_id,
        prestacion_id=prestacion_id,
    )

    inicio_utc = asegurar_utc(inicio)
    fin_calculado = calcular_fin_turno(inicio_utc, prestacion.duracion_min)
    fin_utc = asegurar_utc(fin) if fin is not None else fin_calculado

    if fin_utc <= inicio_utc:
        raise EntidadInvalida("La hora de fin del turno tiene que ser posterior al inicio.")

    obs_limpia = observaciones.strip() if observaciones else None
    if sobreturno and not obs_limpia:
        raise EntidadInvalida(
            "Para agendar un sobreturno tenés que especificar el motivo en observaciones."
        )

    await verificar_disponibilidad(
        session,
        tenant_id=tenant_id,
        profesional_id=profesional_id,
        sillon_id=sillon_id,
        inicio=inicio_utc,
        fin=fin_utc,
        duracion_min=prestacion.duracion_min,
        sobreturno=sobreturno,
    )

    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        profesional_id=profesional_id,
        sillon_id=sillon_id,
        prestacion_id=prestacion_id,
        inicio=inicio_utc,
        fin=fin_utc,
        estado=EstadoTurno.PENDIENTE.value,
        origen=origen.value,
        sobreturno=sobreturno,
        observaciones=obs_limpia,
        turno_origen_id=turno_origen_id,
        sena_cobrada=sena_cobrada,
    )
    session.add(turno)
    await session.flush()

    # RN-PA-02: una prestación que exige seña genera la seña `pendiente` del turno.
    # Un turno reprogramado con la seña ya cobrada no genera otra (1:1 con el turno).
    if prestacion.requiere_sena and not sena_cobrada:
        from app.application.caja import generar_sena_pendiente

        await generar_sena_pendiente(
            session,
            tenant_id=tenant_id,
            turno=turno,
            prestacion=prestacion,
            actor_id=actor_id,
        )

    token = await crear_token_gestion(
        session,
        tenant_id=tenant_id,
        recurso="turno",
        recurso_id=str(turno.id),
        vence_at=fin_utc + timedelta(days=DIAS_VENCIMIENTO_TOKEN_TURNO),
    )

    accion_auditoria = "turno.crear_sobreturno" if sobreturno else "turno.crear"
    despues: dict[str, object] = {
        "estado": turno.estado,
        "origen": turno.origen,
        "inicio": turno.inicio.isoformat(),
        "fin": turno.fin.isoformat(),
        "profesional_id": str(turno.profesional_id),
        "sillon_id": str(turno.sillon_id),
        "prestacion_id": str(turno.prestacion_id),
        "sobreturno": turno.sobreturno,
        "override_duracion": fin is not None and fin_utc != fin_calculado,
    }
    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion=accion_auditoria,
        entidad="turno",
        entidad_id=str(turno.id),
        despues=despues,
    )
    return turno, token


async def cambiar_estado_turno(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID,
    nuevo_estado: EstadoTurno,
    motivo_cancelacion: str | None = None,
    sena_cobrada: bool | None = None,
    idempotente: bool = False,
    actor_id: uuid.UUID | None = None,
) -> Turno:
    """Ejecuta una transición en la máquina de estados del turno (RN-AG-07, RN-PA-01, RN-AG-08)."""
    turno = (
        await session.execute(
            select(Turno).where(Turno.id == turno_id, Turno.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if turno is None:
        raise NoEncontrado("Che, no encontramos ese turno en el consultorio.")

    if sena_cobrada is not None:
        turno.sena_cobrada = sena_cobrada

    estado_actual = EstadoTurno(turno.estado)
    if idempotente and estado_actual == nuevo_estado:
        return turno

    if not es_transicion_valida(estado_actual, nuevo_estado):
        raise EntidadInvalida(
            f"Che, no se puede pasar un turno de '{estado_actual.value}' a '{nuevo_estado.value}'."
        )

    if nuevo_estado == EstadoTurno.CONFIRMADO:
        prestacion = await session.get(Prestacion, turno.prestacion_id)
        if prestacion is not None and prestacion.requiere_sena and not turno.sena_cobrada:
            raise Conflicto("Che, este turno requiere abonar la seña antes de poder confirmarlo.")

    if nuevo_estado == EstadoTurno.PRESENTE:
        prestacion_turno = await session.get(Prestacion, turno.prestacion_id)
        if prestacion_turno is not None and prestacion_turno.invasiva:
            from app.application.clinica import tiene_consentimiento_vigente

            vigente = await tiene_consentimiento_vigente(
                session,
                tenant_id=tenant_id,
                paciente_id=turno.paciente_id,
                prestacion_id=turno.prestacion_id,
                turno_id=turno.id,
            )
            if not vigente:
                raise Conflicto(
                    "Che, esta prestación es invasiva y requiere el consentimiento informado "
                    "firmado antes de iniciar la atención."
                )

    antes: dict[str, object] = {
        "estado": turno.estado,
        "sena_cobrada": turno.sena_cobrada,
    }
    turno.estado = nuevo_estado.value
    if motivo_cancelacion:
        turno.motivo_cancelacion = motivo_cancelacion.strip()
    await session.flush()

    despues: dict[str, object] = {
        "estado": turno.estado,
        "sena_cobrada": turno.sena_cobrada,
        "motivo_cancelacion": turno.motivo_cancelacion,
    }
    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="turno.cambiar_estado",
        entidad="turno",
        entidad_id=str(turno.id),
        antes=antes,
        despues=despues,
    )

    if nuevo_estado in (EstadoTurno.CANCELADO, EstadoTurno.AUSENTE):
        from app.application.lista_espera import ofrecer_hueco_lista_espera

        await ofrecer_hueco_lista_espera(
            session,
            tenant_id=tenant_id,
            prestacion_id=turno.prestacion_id,
            profesional_id=turno.profesional_id,
            sillon_id=turno.sillon_id,
            inicio=turno.inicio,
            fin=turno.fin,
            actor_id=actor_id,
        )

    return turno


async def _verificar_anticipacion_minima(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    inicio_turno: datetime,
    ahora: datetime | None = None,
) -> None:
    """Verifica que falten al menos `cancelacion_hs` horas antes del inicio del turno (RN-AG-05)."""
    tenant = await session.get(Tenant, tenant_id)
    politicas = (tenant.politicas if tenant and isinstance(tenant.politicas, dict) else {}) or {}
    raw_hs = politicas.get("cancelacion_hs", 24)
    cancelacion_hs = raw_hs if isinstance(raw_hs, int) else 24
    ahora_utc = asegurar_utc(ahora) if ahora is not None else datetime.now(UTC)
    inicio_utc = asegurar_utc(inicio_turno)

    if inicio_utc - ahora_utc < timedelta(hours=cancelacion_hs):
        raise Conflicto(
            f"Che, estás fuera de término: los cambios o cancelaciones requieren "
            f"al menos {cancelacion_hs} horas de anticipación."
        )


async def cancelar_turno_publico(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID,
    motivo: str | None = None,
    ahora: datetime | None = None,
) -> Turno:
    """Cancela un turno desde el canal público verificando anticipación mínima (RN-AG-05)."""
    turno = (
        await session.execute(
            select(Turno).where(Turno.id == turno_id, Turno.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if turno is None:
        raise NoEncontrado("Che, no encontramos ese turno.")

    await _verificar_anticipacion_minima(
        session,
        tenant_id=tenant_id,
        inicio_turno=turno.inicio,
        ahora=ahora,
    )
    return await cambiar_estado_turno(
        session,
        tenant_id=tenant_id,
        turno_id=turno_id,
        nuevo_estado=EstadoTurno.CANCELADO,
        motivo_cancelacion=motivo,
    )


async def reprogramar_turno(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID,
    nuevo_inicio: datetime,
    profesional_id: uuid.UUID | None = None,
    sillon_id: uuid.UUID | None = None,
    motivo: str | None = None,
    actor_id: uuid.UUID | None = None,
    validar_anticipacion: bool = False,
    ahora: datetime | None = None,
) -> tuple[Turno, str]:
    """Reprograma en 1 clic pasando el turno a `reprogramado` y creando uno nuevo (RN-AG-06)."""
    turno_orig = (
        await session.execute(
            select(Turno).where(Turno.id == turno_id, Turno.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if turno_orig is None:
        raise NoEncontrado("Che, no encontramos el turno a reprogramar.")

    if not es_transicion_valida(turno_orig.estado, EstadoTurno.REPROGRAMADO):
        raise EntidadInvalida(
            f"Che, no se puede reprogramar un turno en estado '{turno_orig.estado}'."
        )

    if validar_anticipacion:
        await _verificar_anticipacion_minima(
            session,
            tenant_id=tenant_id,
            inicio_turno=turno_orig.inicio,
            ahora=ahora,
        )

    prof_destino = profesional_id or turno_orig.profesional_id
    sillon_destino = sillon_id or turno_orig.sillon_id
    prestacion = await session.get(Prestacion, turno_orig.prestacion_id)
    if prestacion is None:
        raise NoEncontrado("Che, la prestación del turno ya no existe.")

    nuevo_inicio_utc = asegurar_utc(nuevo_inicio)
    nuevo_fin_utc = calcular_fin_turno(nuevo_inicio_utc, prestacion.duracion_min)

    await verificar_disponibilidad(
        session,
        tenant_id=tenant_id,
        profesional_id=prof_destino,
        sillon_id=sillon_destino,
        inicio=nuevo_inicio_utc,
        fin=nuevo_fin_utc,
        duracion_min=prestacion.duracion_min,
        sobreturno=False,
        excluir_turno_id=turno_orig.id,
    )

    estado_anterior = turno_orig.estado
    turno_orig.estado = EstadoTurno.REPROGRAMADO.value
    if motivo:
        turno_orig.motivo_cancelacion = motivo.strip()
    await session.flush()

    nuevo_turno, nuevo_token = await crear_turno(
        session,
        tenant_id=tenant_id,
        paciente_id=turno_orig.paciente_id,
        profesional_id=prof_destino,
        sillon_id=sillon_destino,
        prestacion_id=turno_orig.prestacion_id,
        inicio=nuevo_inicio_utc,
        origen=OrigenTurno(turno_orig.origen),
        sena_cobrada=turno_orig.sena_cobrada,
        turno_origen_id=turno_orig.id,
        actor_id=actor_id,
    )

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="turno.reprogramar",
        entidad="turno",
        entidad_id=str(turno_orig.id),
        antes={"estado": estado_anterior, "inicio": asegurar_utc(turno_orig.inicio).isoformat()},
        despues={
            "estado": turno_orig.estado,
            "nuevo_turno_id": str(nuevo_turno.id),
            "nuevo_inicio": nuevo_turno.inicio.isoformat(),
        },
    )

    from app.application.lista_espera import ofrecer_hueco_lista_espera

    await ofrecer_hueco_lista_espera(
        session,
        tenant_id=tenant_id,
        prestacion_id=turno_orig.prestacion_id,
        profesional_id=turno_orig.profesional_id,
        sillon_id=turno_orig.sillon_id,
        inicio=turno_orig.inicio,
        fin=turno_orig.fin,
        ahora=ahora,
        actor_id=actor_id,
    )
    return nuevo_turno, nuevo_token


async def crear_bloqueo(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    profesional_id: uuid.UUID | None,
    sillon_id: uuid.UUID | None,
    desde: datetime,
    hasta: datetime,
    motivo: MotivoBloqueo = MotivoBloqueo.MANUAL,
    descripcion: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> Bloqueo:
    """Crea un bloqueo horario de profesional y/o sillón y lo audita (RN-AG-03)."""
    if profesional_id is None and sillon_id is None:
        raise EntidadInvalida(
            "Tenés que indicar al menos un profesional o un sillón para crear el bloqueo."
        )
    desde_utc = asegurar_utc(desde)
    hasta_utc = asegurar_utc(hasta)
    if hasta_utc <= desde_utc:
        raise EntidadInvalida("La fecha/hora hasta del bloqueo tiene que ser posterior a desde.")

    if profesional_id is not None:
        prof = (
            await session.execute(
                select(Usuario).where(Usuario.id == profesional_id, Usuario.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if prof is None:
            raise NoEncontrado("Che, ese profesional no pertenece al consultorio.")

    if sillon_id is not None:
        sillon = (
            await session.execute(
                select(Sillon).where(Sillon.id == sillon_id, Sillon.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if sillon is None:
            raise NoEncontrado("Che, ese sillón no pertenece al consultorio.")

    bloqueo = Bloqueo(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        profesional_id=profesional_id,
        sillon_id=sillon_id,
        desde=desde_utc,
        hasta=hasta_utc,
        motivo=motivo.value,
        descripcion=descripcion.strip() if descripcion else None,
        created_by=actor_id,
    )
    session.add(bloqueo)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="bloqueo.crear",
        entidad="bloqueo",
        entidad_id=str(bloqueo.id),
        despues={
            "profesional_id": str(profesional_id) if profesional_id else None,
            "sillon_id": str(sillon_id) if sillon_id else None,
            "desde": desde_utc.isoformat(),
            "hasta": hasta_utc.isoformat(),
            "motivo": bloqueo.motivo,
        },
    )
    return bloqueo
