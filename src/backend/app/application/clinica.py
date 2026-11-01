"""Casos de uso de Historia Clínica, Odontograma FDI y Consentimiento Informado (C-09, Flujo 3).

Reglas implementadas:
- RN-CL-01 / R7: La HC no admite hard delete ni edición destructiva; actualizar la ficha genera una
  Evolución automática y un evento de Auditoría; evoluciones y eventos son append-only.
- RN-CL-02: Las prestaciones invasivas exigen un Consentimiento firmado vigente antes de
  iniciar la atención (pasar el turno a estado `presente`).
- RN-SE-01 / R9: Auditoría append-only sin exponer PHI (notas, alergias, firmas) en logs
  ni en los payloads de auditoría.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_clinica import (
    AdjuntoCreate,
    ConsentimientoCreate,
    ConsentimientoFirmaInput,
    ConsentimientoPublicoRead,
    EstadoPiezaFDIRead,
    EvolucionCreate,
    FichaClinicaUpdate,
    OdontogramaRead,
    PiezaEventoCreate,
    PiezaEventoRead,
)
from app.application.auditoria import registrar_auditoria
from app.domain.clinica import (
    AdjuntoClinico,
    CanalFirmaConsentimiento,
    Consentimiento,
    Evolucion,
    Odontograma,
    PiezaEvento,
    calcular_hash_consentimiento,
    es_pieza_fdi_valida,
)
from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.turno import Turno
from app.infrastructure.security.tokens_publicos import (
    crear_token_gestion,
    marcar_usado,
    resolver_token_gestion_recurso,
)
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

RECURSO_TOKEN_CONSENTIMIENTO = "consentimiento"
DIAS_VIGENCIA_TOKEN_CONSENTIMIENTO = 30


async def obtener_ficha_clinica(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
) -> FichaClinica:
    """Obtiene la ficha clínica 1:1 de un paciente (o la inicializa si faltara)."""
    paciente = (
        await session.execute(
            select(Paciente).where(Paciente.id == paciente_id, Paciente.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente solicitado en este consultorio.")

    ficha = (
        await session.execute(
            select(FichaClinica).where(
                FichaClinica.tenant_id == tenant_id,
                FichaClinica.paciente_id == paciente_id,
            )
        )
    ).scalar_one_or_none()
    if ficha is None:
        ficha = FichaClinica(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            paciente_id=paciente_id,
        )
        session.add(ficha)
        await session.flush()
    return ficha


async def actualizar_ficha_clinica(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    datos: FichaClinicaUpdate,
    actor_id: uuid.UUID,
) -> FichaClinica:
    """Actualiza la anamnesis/ficha clínica y genera Evolucion + Auditoria (RN-CL-01, R9)."""
    ficha = await obtener_ficha_clinica(session, tenant_id=tenant_id, paciente_id=paciente_id)
    cambios = datos.model_dump(exclude_unset=True)
    nota_extra = cambios.pop("nota_evolucion", None)

    campos_modificados: list[str] = []
    for campo in ("antecedentes", "alergias", "medicacion", "habitos", "datos_json"):
        if campo in cambios and getattr(ficha, campo) != cambios[campo]:
            setattr(ficha, campo, cambios[campo])
            campos_modificados.append(campo)

    if not campos_modificados and not nota_extra:
        return ficha

    ficha.updated_at = datetime.now(UTC)
    await session.flush()

    resumen_campos = (
        ", ".join(campos_modificados) if campos_modificados else "sin cambios de campos"
    )
    texto_evolucion = f"Actualización de anamnesis ({resumen_campos})."
    if isinstance(nota_extra, str) and nota_extra.strip():
        texto_evolucion = f"{texto_evolucion} {nota_extra.strip()}"

    evolucion = Evolucion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ficha_clinica_id=ficha.id,
        paciente_id=paciente_id,
        profesional_id=actor_id,
        nota=texto_evolucion,
    )
    session.add(evolucion)
    await session.flush()

    # R9: Nunca incluir el texto de alergias/antecedentes/medicación en Auditoria
    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="ficha_clinica.actualizar",
        entidad="ficha_clinica",
        entidad_id=str(ficha.id),
        antes={"paciente_id": str(paciente_id)},
        despues={
            "paciente_id": str(paciente_id),
            "campos_modificados": campos_modificados,
            "evolucion_id": str(evolucion.id),
        },
    )
    return ficha


async def listar_evoluciones_paciente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
) -> list[Evolucion]:
    """Lista las evoluciones clínicas de un paciente en orden cronológico."""
    await obtener_ficha_clinica(session, tenant_id=tenant_id, paciente_id=paciente_id)
    filas = (
        (
            await session.execute(
                select(Evolucion)
                .where(
                    Evolucion.tenant_id == tenant_id,
                    Evolucion.paciente_id == paciente_id,
                )
                .order_by(Evolucion.created_at.asc(), Evolucion.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(filas)


async def crear_evolucion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    datos: EvolucionCreate,
    actor_id: uuid.UUID,
) -> Evolucion:
    """Registra una nueva evolución append-only o una enmienda aditiva (RN-CL-01, R7)."""
    ficha = await obtener_ficha_clinica(session, tenant_id=tenant_id, paciente_id=paciente_id)

    if datos.turno_id is not None:
        turno = (
            await session.execute(
                select(Turno).where(
                    Turno.id == datos.turno_id,
                    Turno.tenant_id == tenant_id,
                    Turno.paciente_id == paciente_id,
                )
            )
        ).scalar_one_or_none()
        if turno is None:
            raise NoEncontrado("Che, el turno indicado no pertenece a este paciente.")

    if datos.es_correccion_de_id is not None:
        ev_orig = (
            await session.execute(
                select(Evolucion).where(
                    Evolucion.id == datos.es_correccion_de_id,
                    Evolucion.tenant_id == tenant_id,
                    Evolucion.paciente_id == paciente_id,
                )
            )
        ).scalar_one_or_none()
        if ev_orig is None:
            raise NoEncontrado("Che, no encontramos la evolución original que querés enmendar.")

    evolucion = Evolucion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ficha_clinica_id=ficha.id,
        paciente_id=paciente_id,
        turno_id=datos.turno_id,
        profesional_id=actor_id,
        nota=datos.nota,
        es_correccion_de_id=datos.es_correccion_de_id,
    )
    session.add(evolucion)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="evolucion.crear",
        entidad="evolucion",
        entidad_id=str(evolucion.id),
        despues={
            "ficha_clinica_id": str(ficha.id),
            "turno_id": str(datos.turno_id) if datos.turno_id else None,
            "es_correccion_de_id": (
                str(datos.es_correccion_de_id) if datos.es_correccion_de_id else None
            ),
        },
    )
    return evolucion


async def crear_adjunto_clinico(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    datos: AdjuntoCreate,
    actor_id: uuid.UUID,
) -> AdjuntoClinico:
    """Registra metadatos de un estudio/adjunto clínico sin exponer PHI en auditoría (R9)."""
    ficha = await obtener_ficha_clinica(session, tenant_id=tenant_id, paciente_id=paciente_id)

    adjunto = AdjuntoClinico(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        ficha_clinica_id=ficha.id,
        evolucion_id=datos.evolucion_id,
        pieza_evento_id=datos.pieza_evento_id,
        tipo=datos.tipo.value,
        nombre_archivo=datos.nombre_archivo,
        mime_type=datos.mime_type,
        tamano_bytes=datos.tamano_bytes,
        storage_key=datos.storage_key,
        created_by=actor_id,
    )
    session.add(adjunto)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="adjunto_clinico.crear",
        entidad="adjunto_clinico",
        entidad_id=str(adjunto.id),
        despues={
            "tipo": adjunto.tipo,
            "mime_type": adjunto.mime_type,
            "tamano_bytes": adjunto.tamano_bytes,
        },
    )
    return adjunto


async def listar_adjuntos_paciente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
) -> list[AdjuntoClinico]:
    """Lista los adjuntos clínicos asociados a la ficha de un paciente."""
    await obtener_ficha_clinica(session, tenant_id=tenant_id, paciente_id=paciente_id)
    filas = (
        (
            await session.execute(
                select(AdjuntoClinico)
                .where(
                    AdjuntoClinico.tenant_id == tenant_id,
                    AdjuntoClinico.paciente_id == paciente_id,
                )
                .order_by(AdjuntoClinico.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(filas)


async def obtener_o_crear_odontograma(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
) -> Odontograma:
    """Obtiene o inicializa el odontograma cabecera 1:1 del paciente."""
    await obtener_ficha_clinica(session, tenant_id=tenant_id, paciente_id=paciente_id)
    odo = (
        await session.execute(
            select(Odontograma).where(
                Odontograma.tenant_id == tenant_id,
                Odontograma.paciente_id == paciente_id,
            )
        )
    ).scalar_one_or_none()
    if odo is None:
        odo = Odontograma(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            paciente_id=paciente_id,
        )
        session.add(odo)
        await session.flush()
    return odo


async def registrar_evento_pieza(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    datos: PiezaEventoCreate,
    actor_id: uuid.UUID,
) -> PiezaEvento:
    """Inserta un nuevo PiezaEvento append-only sobre el odontograma del paciente (RN-CL-01)."""
    if not es_pieza_fdi_valida(datos.pieza_fdi):
        raise EntidadInvalida(f"Che, la pieza FDI '{datos.pieza_fdi}' no es válida.")

    odo = await obtener_o_crear_odontograma(session, tenant_id=tenant_id, paciente_id=paciente_id)
    odo.updated_at = datetime.now(UTC)

    evento = PiezaEvento(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        odontograma_id=odo.id,
        pieza_fdi=datos.pieza_fdi,
        superficie=datos.superficie.value,
        evento=datos.evento.value,
        turno_id=datos.turno_id,
        observacion=datos.observacion,
        created_by=actor_id,
    )
    session.add(evento)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="odontograma.registrar_evento",
        entidad="pieza_evento",
        entidad_id=str(evento.id),
        despues={
            "odontograma_id": str(odo.id),
            "pieza_fdi": evento.pieza_fdi,
            "superficie": evento.superficie,
            "evento": evento.evento,
            "turno_id": str(evento.turno_id) if evento.turno_id else None,
        },
    )
    return evento


async def obtener_odontograma_paciente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
) -> OdontogramaRead:
    """Devuelve el odontograma FDI del paciente con el estado proyectado por pieza/superficie."""
    odo = await obtener_o_crear_odontograma(session, tenant_id=tenant_id, paciente_id=paciente_id)
    eventos = (
        (
            await session.execute(
                select(PiezaEvento)
                .where(
                    PiezaEvento.tenant_id == tenant_id,
                    PiezaEvento.odontograma_id == odo.id,
                )
                .order_by(PiezaEvento.created_at.asc(), PiezaEvento.id.asc())
            )
        )
        .scalars()
        .all()
    )

    superficies_por_pieza: dict[int, dict[str, str]] = {}
    ultimo_evento_por_pieza: dict[int, tuple[uuid.UUID, datetime]] = {}
    for ev in eventos:
        mapa_sup = superficies_por_pieza.setdefault(ev.pieza_fdi, {})
        mapa_sup[ev.superficie] = ev.evento
        ultimo_evento_por_pieza[ev.pieza_fdi] = (ev.id, ev.created_at)

    piezas_proyectadas = [
        EstadoPiezaFDIRead(
            pieza_fdi=pieza,
            superficies=superficies_por_pieza[pieza],
            ultimo_evento_id=ultimo_evento_por_pieza[pieza][0],
            updated_at=ultimo_evento_por_pieza[pieza][1],
        )
        for pieza in sorted(superficies_por_pieza.keys())
    ]

    return OdontogramaRead(
        odontograma_id=odo.id,
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        piezas=piezas_proyectadas,
        eventos=[PiezaEventoRead.model_validate(e) for e in eventos],
    )


async def listar_historial_pieza(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    pieza_fdi: int,
) -> list[PiezaEvento]:
    """Devuelve la secuencia cronológica inmutable de eventos de una pieza FDI."""
    if not es_pieza_fdi_valida(pieza_fdi):
        raise EntidadInvalida(f"Che, la pieza FDI '{pieza_fdi}' no es válida.")

    odo = await obtener_o_crear_odontograma(session, tenant_id=tenant_id, paciente_id=paciente_id)
    filas = (
        (
            await session.execute(
                select(PiezaEvento)
                .where(
                    PiezaEvento.tenant_id == tenant_id,
                    PiezaEvento.odontograma_id == odo.id,
                    PiezaEvento.pieza_fdi == pieza_fdi,
                )
                .order_by(PiezaEvento.created_at.asc(), PiezaEvento.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(filas)


async def crear_consentimiento(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    datos: ConsentimientoCreate,
    actor_id: uuid.UUID,
) -> tuple[Consentimiento, str]:
    """Emite un consentimiento informado pendiente de firma junto con su TokenGestion público."""
    paciente = (
        await session.execute(
            select(Paciente).where(
                Paciente.id == datos.paciente_id,
                Paciente.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente para emitir el consentimiento.")

    prestacion = (
        await session.execute(
            select(Prestacion).where(
                Prestacion.id == datos.prestacion_id,
                Prestacion.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if prestacion is None:
        raise NoEncontrado("Che, no encontramos la prestación indicada para el consentimiento.")

    cons = Consentimiento(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=datos.paciente_id,
        prestacion_id=datos.prestacion_id,
        turno_id=datos.turno_id,
        texto_version=datos.texto_version,
        texto_contenido=datos.texto_contenido,
        canal=CanalFirmaConsentimiento.PRESENCIAL.value,
        revocado=False,
    )
    session.add(cons)
    await session.flush()

    token_claro = await crear_token_gestion(
        session,
        tenant_id=tenant_id,
        recurso=RECURSO_TOKEN_CONSENTIMIENTO,
        recurso_id=str(cons.id),
        vence_at=datetime.now(UTC) + timedelta(days=DIAS_VIGENCIA_TOKEN_CONSENTIMIENTO),
    )

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="consentimiento.crear",
        entidad="consentimiento",
        entidad_id=str(cons.id),
        despues={
            "paciente_id": str(cons.paciente_id),
            "prestacion_id": str(cons.prestacion_id),
            "turno_id": str(cons.turno_id) if cons.turno_id else None,
            "texto_version": cons.texto_version,
        },
    )
    return cons, token_claro


async def listar_consentimientos(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID | None = None,
    turno_id: uuid.UUID | None = None,
) -> list[Consentimiento]:
    """Lista los consentimientos informados del consultorio filtrables por paciente o turno."""
    stmt = select(Consentimiento).where(Consentimiento.tenant_id == tenant_id)
    if paciente_id is not None:
        stmt = stmt.where(Consentimiento.paciente_id == paciente_id)
    if turno_id is not None:
        stmt = stmt.where(Consentimiento.turno_id == turno_id)
    stmt = stmt.order_by(Consentimiento.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def firmar_consentimiento(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    consentimiento_id: uuid.UUID,
    datos: ConsentimientoFirmaInput,
    actor_id: uuid.UUID | None = None,
) -> Consentimiento:
    """Registra la firma de un consentimiento informado calculando su firma_hash SHA-256."""
    cons = (
        await session.execute(
            select(Consentimiento).where(
                Consentimiento.id == consentimiento_id,
                Consentimiento.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if cons is None:
        raise NoEncontrado("Che, no encontramos el consentimiento informado.")
    if cons.revocado:
        raise Conflicto("Che, este consentimiento fue revocado; generá uno nuevo para firmar.")
    if cons.firmado_at is not None:
        return cons

    ahora = datetime.now(UTC)
    cons.firmado_por = datos.firmado_por
    cons.firmado_at = ahora
    cons.canal = datos.canal.value
    cons.firma_hash = calcular_hash_consentimiento(
        tenant_id=tenant_id,
        paciente_id=cons.paciente_id,
        prestacion_id=cons.prestacion_id,
        texto_version=cons.texto_version,
        firmado_por=datos.firmado_por,
        firmado_at=ahora,
        firma_datos=datos.firma_datos,
    )
    cons.updated_at = ahora
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="consentimiento.firmar",
        entidad="consentimiento",
        entidad_id=str(cons.id),
        despues={
            "canal": cons.canal,
            "firma_hash": cons.firma_hash,
            "firmado_at": ahora.isoformat(),
        },
    )
    return cons


async def obtener_consentimiento_por_token(
    session: AsyncSession,
    *,
    token: str,
) -> ConsentimientoPublicoRead:
    """Obtiene la vista pública mínima de un consentimiento mediante su token_gestion (RN-SE-03)."""
    fila_token = await resolver_token_gestion_recurso(
        session, token=token, recurso=RECURSO_TOKEN_CONSENTIMIENTO
    )
    cons_id = uuid.UUID(fila_token.recurso_id)
    cons = (
        await session.execute(
            select(Consentimiento).where(
                Consentimiento.id == cons_id,
                Consentimiento.tenant_id == fila_token.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if cons is None:
        raise NoEncontrado("Che, no encontramos el consentimiento asociado a este link.")

    return ConsentimientoPublicoRead(
        consentimiento_id=cons.id,
        prestacion_id=cons.prestacion_id,
        texto_version=cons.texto_version,
        texto_contenido=cons.texto_contenido,
        firmado=cons.firmado_at is not None,
        firmado_at=cons.firmado_at,
        revocado=cons.revocado,
    )


async def firmar_consentimiento_por_token(
    session: AsyncSession,
    *,
    token: str,
    datos: ConsentimientoFirmaInput,
) -> Consentimiento:
    """Firma un consentimiento informado usando su TokenGestion público (`/firmar/{token}`)."""
    fila_token = await resolver_token_gestion_recurso(
        session, token=token, recurso=RECURSO_TOKEN_CONSENTIMIENTO
    )
    cons_id = uuid.UUID(fila_token.recurso_id)
    datos_token = ConsentimientoFirmaInput(
        firmado_por=datos.firmado_por,
        firma_datos=datos.firma_datos,
        canal=CanalFirmaConsentimiento.TOKEN,
    )
    cons = await firmar_consentimiento(
        session,
        tenant_id=fila_token.tenant_id,
        consentimiento_id=cons_id,
        datos=datos_token,
        actor_id=None,
    )
    await marcar_usado(session, fila_token)
    return cons


async def revocar_consentimiento(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    consentimiento_id: uuid.UUID,
    motivo: str,
    actor_id: uuid.UUID,
) -> Consentimiento:
    """Revoca un consentimiento informado dejando constancia en Auditoria (RN-CL-02)."""
    cons = (
        await session.execute(
            select(Consentimiento).where(
                Consentimiento.id == consentimiento_id,
                Consentimiento.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if cons is None:
        raise NoEncontrado("Che, no encontramos el consentimiento que querés revocar.")

    ahora = datetime.now(UTC)
    cons.revocado = True
    cons.revocado_motivo = motivo.strip()
    cons.revocado_at = ahora
    cons.updated_at = ahora
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="consentimiento.revocar",
        entidad="consentimiento",
        entidad_id=str(cons.id),
        antes={"revocado": False},
        despues={"revocado": True, "revocado_at": ahora.isoformat()},
    )
    return cons


async def tiene_consentimiento_vigente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    turno_id: uuid.UUID | None = None,
) -> bool:
    """Devuelve True si el paciente posee un consentimiento firmado vigente para la prestación."""
    condicion_turno = (
        or_(Consentimiento.turno_id == turno_id, Consentimiento.turno_id.is_(None))
        if turno_id is not None
        else Consentimiento.turno_id.is_(None)
    )
    fila = (
        await session.execute(
            select(Consentimiento.id)
            .where(
                Consentimiento.tenant_id == tenant_id,
                Consentimiento.paciente_id == paciente_id,
                Consentimiento.prestacion_id == prestacion_id,
                Consentimiento.firmado_at.is_not(None),
                Consentimiento.revocado.is_(False),
                condicion_turno,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return fila is not None
