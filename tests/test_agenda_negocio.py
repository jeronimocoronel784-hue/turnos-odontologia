"""Tests de reglas de negocio de Agenda y Turnos (tarea 2.1).

Verifica:
- RN-AG-01: anti-solapamiento por profesional y por sillón con slots alternativos (RN-GL-02).
- RN-AG-02: cálculo de fin según duración de la prestación.
- RN-AG-03: bloqueo horario impide agendar (incluso con sobreturno=True).
- RN-AG-04: sobreturno explícito con motivo permite solapar otro turno y queda auditado.
- RN-AG-05 / RN-AG-06: reprogramación 1-clic preserva turno original y valida anticipación mínima.
- RN-AG-07 / RN-PA-01 / RN-AG-08: grafo de estados, seña obligatoria e idempotencia al confirmar.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda import (
    cambiar_estado_turno,
    cancelar_turno_publico,
    crear_bloqueo,
    crear_turno,
    reprogramar_turno,
)
from app.domain.auditoria import Auditoria
from app.domain.bloqueo import MotivoBloqueo
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, Turno
from app.domain.usuario import RolUsuario, Usuario
from app.shared.exceptions import Conflicto, ConflictoDisponibilidad, EntidadInvalida


async def _seed_agenda(
    session: AsyncSession,
) -> tuple[Tenant, Usuario, Usuario, Sillon, Sillon, Prestacion, Prestacion, Paciente]:
    tenant = Tenant(
        nombre="Consultorio Agenda",
        slug=f"ag-{uuid.uuid4().hex[:6]}",
        politicas={"anticipacion_min_hs": 2, "cancelacion_hs": 24, "sena_default": 0},
    )
    session.add(tenant)
    await session.flush()

    prof1 = Usuario(
        tenant_id=tenant.id,
        nombre="Dra. Laura",
        email="laura@odonto.test",
        password_hash="hash",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MN-1001",
    )
    prof2 = Usuario(
        tenant_id=tenant.id,
        nombre="Dr. Martin",
        email="martin@odonto.test",
        password_hash="hash",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MN-1002",
    )
    sillon1 = Sillon(tenant_id=tenant.id, nombre="Box 1", sucursal="central")
    sillon2 = Sillon(tenant_id=tenant.id, nombre="Box 2", sucursal="central")
    prest_consulta = Prestacion(
        tenant_id=tenant.id,
        nombre="Consulta General",
        duracion_min=30,
        precio_particular=Decimal("15000.00"),
        requiere_sena=False,
    )
    prest_endo = Prestacion(
        tenant_id=tenant.id,
        nombre="Endodoncia",
        duracion_min=60,
        precio_particular=Decimal("80000.00"),
        requiere_sena=True,
        monto_sena=Decimal("20000.00"),
    )
    paciente = Paciente(
        tenant_id=tenant.id,
        nombre="Carlos Gomez",
        dni="33444555",
        telefono="1144556677",
    )
    session.add_all([prof1, prof2, sillon1, sillon2, prest_consulta, prest_endo, paciente])
    await session.commit()
    return tenant, prof1, prof2, sillon1, sillon2, prest_consulta, prest_endo, paciente


@pytest.mark.asyncio
async def test_crear_turno_calcula_fin_y_rechaza_solapamiento_con_alternativas(
    session: AsyncSession,
) -> None:
    (
        tenant,
        prof1,
        prof2,
        sillon1,
        sillon2,
        prest_consulta,
        _,
        paciente,
    ) = await _seed_agenda(session)

    inicio = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    turno1, token1 = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=prof1.id,
        sillon_id=sillon1.id,
        prestacion_id=prest_consulta.id,
        inicio=inicio,
        actor_id=prof1.id,
    )
    await session.commit()

    # RN-AG-02: 30 min -> fin 10:30
    assert turno1.fin == datetime(2026, 11, 16, 10, 30, tzinfo=UTC)
    assert token1 is not None and len(token1) > 20

    # Solapamiento por profesional (mismo prof1, otro sillón sillon2, a las 10:15) -> 409 con slots
    with pytest.raises(ConflictoDisponibilidad) as exc_prof:
        await crear_turno(
            session,
            tenant_id=tenant.id,
            paciente_id=paciente.id,
            profesional_id=prof1.id,
            sillon_id=sillon2.id,
            prestacion_id=prest_consulta.id,
            inicio=datetime(2026, 11, 16, 10, 15, tzinfo=UTC),
            actor_id=prof1.id,
        )
    assert exc_prof.value.status_code == 409
    assert len(exc_prof.value.slots_alternativos) > 0

    # Solapamiento por sillón (otro profesional prof2, mismo sillon1, a las 10:00) -> 409 con slots
    with pytest.raises(ConflictoDisponibilidad) as exc_sillon:
        await crear_turno(
            session,
            tenant_id=tenant.id,
            paciente_id=paciente.id,
            profesional_id=prof2.id,
            sillon_id=sillon1.id,
            prestacion_id=prest_consulta.id,
            inicio=inicio,
            actor_id=prof2.id,
        )
    assert exc_sillon.value.status_code == 409
    assert len(exc_sillon.value.slots_alternativos) > 0

    # Sobreturno explícito con motivo (RN-AG-04) sí permite solapar otro turno
    turno_sobre, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=prof1.id,
        sillon_id=sillon1.id,
        prestacion_id=prest_consulta.id,
        inicio=inicio,
        sobreturno=True,
        observaciones="Urgencia por trauma dental",
        actor_id=prof1.id,
    )
    await session.commit()
    assert turno_sobre.sobreturno is True


@pytest.mark.asyncio
async def test_bloqueo_impide_turno_normal_y_sobreturno_rn_ag_03(
    session: AsyncSession,
) -> None:
    (
        tenant,
        prof1,
        _,
        sillon1,
        _,
        prest_consulta,
        _,
        paciente,
    ) = await _seed_agenda(session)

    desde = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
    hasta = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    await crear_bloqueo(
        session,
        tenant_id=tenant.id,
        profesional_id=prof1.id,
        sillon_id=None,
        desde=desde,
        hasta=hasta,
        motivo=MotivoBloqueo.VACACIONES,
        descripcion="Congreso odontológico",
        actor_id=prof1.id,
    )
    await session.commit()

    # Ni siquiera con sobreturno=True se puede agendar sobre un bloqueo
    with pytest.raises(ConflictoDisponibilidad) as exc:
        await crear_turno(
            session,
            tenant_id=tenant.id,
            paciente_id=paciente.id,
            profesional_id=prof1.id,
            sillon_id=sillon1.id,
            prestacion_id=prest_consulta.id,
            inicio=datetime(2026, 11, 17, 10, 0, tzinfo=UTC),
            sobreturno=True,
            observaciones="Intento sobre bloqueo",
            actor_id=prof1.id,
        )
    assert exc.value.status_code == 409
    assert len(exc.value.slots_alternativos) > 0
    # Todos los slots alternativos deben ser >= 12:00 (fuera del bloqueo)
    for slot in exc.value.slots_alternativos:
        assert slot["inicio"] >= hasta.isoformat() or slot["fin"] <= desde.isoformat()


@pytest.mark.asyncio
async def test_grafo_estados_sena_exigible_e_idempotencia_rn_ag_07_pa_01(
    session: AsyncSession,
) -> None:
    (
        tenant,
        prof1,
        _,
        sillon1,
        _,
        _,
        prest_endo,
        paciente,
    ) = await _seed_agenda(session)

    inicio = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)
    turno, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=prof1.id,
        sillon_id=sillon1.id,
        prestacion_id=prest_endo.id,
        inicio=inicio,
        actor_id=prof1.id,
    )
    await session.commit()

    # 1. Prestación con requiere_sena=True e impaga NO puede pasar a confirmado (RN-PA-01)
    with pytest.raises(Conflicto) as exc_sena:
        await cambiar_estado_turno(
            session,
            tenant_id=tenant.id,
            turno_id=turno.id,
            nuevo_estado=EstadoTurno.CONFIRMADO,
            actor_id=prof1.id,
        )
    assert "seña" in exc_sena.value.mensaje.lower()

    # 2. Acreditando la seña pasa a confirmado
    turno = await cambiar_estado_turno(
        session,
        tenant_id=tenant.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.CONFIRMADO,
        sena_cobrada=True,
        actor_id=prof1.id,
    )
    await session.commit()
    assert turno.estado == EstadoTurno.CONFIRMADO.value
    assert turno.sena_cobrada is True

    # 3. Confirmar dos veces con idempotente=True (RN-AG-08) no falla ni duplica transición
    turno_idem = await cambiar_estado_turno(
        session,
        tenant_id=tenant.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.CONFIRMADO,
        idempotente=True,
        actor_id=prof1.id,
    )
    assert turno_idem.estado == EstadoTurno.CONFIRMADO.value

    # 4. confirmado -> presente -> finalizado
    turno = await cambiar_estado_turno(
        session,
        tenant_id=tenant.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.PRESENTE,
        actor_id=prof1.id,
    )
    assert turno.estado == EstadoTurno.PRESENTE.value

    turno = await cambiar_estado_turno(
        session,
        tenant_id=tenant.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.FINALIZADO,
        actor_id=prof1.id,
    )
    await session.commit()
    assert turno.estado == EstadoTurno.FINALIZADO.value

    # 5. Estado terminal finalizado -> cualquier otro estado se rechaza con 422 (RN-AG-07)
    with pytest.raises(EntidadInvalida):
        await cambiar_estado_turno(
            session,
            tenant_id=tenant.id,
            turno_id=turno.id,
            nuevo_estado=EstadoTurno.CANCELADO,
            actor_id=prof1.id,
        )


@pytest.mark.asyncio
async def test_reprogramacion_crea_nuevo_con_turno_origen_y_valida_anticipacion(
    session: AsyncSession,
) -> None:
    (
        tenant,
        prof1,
        _,
        sillon1,
        _,
        prest_consulta,
        _,
        paciente,
    ) = await _seed_agenda(session)

    ahora = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    inicio_original = ahora + timedelta(hours=48)  # 48h adelante (> 24h de cancelacion_hs)
    turno_orig, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=prof1.id,
        sillon_id=sillon1.id,
        prestacion_id=prest_consulta.id,
        inicio=inicio_original,
        actor_id=prof1.id,
    )
    await session.commit()

    nuevo_inicio = inicio_original + timedelta(days=1)
    nuevo_turno, nuevo_token = await reprogramar_turno(
        session,
        tenant_id=tenant.id,
        turno_id=turno_orig.id,
        nuevo_inicio=nuevo_inicio,
        actor_id=prof1.id,
        validar_anticipacion=True,
        ahora=ahora,
    )
    await session.commit()

    # El original queda en reprogramado con su horario intacto (RN-AG-06)
    orig_db = await session.get(Turno, turno_orig.id)
    assert orig_db is not None
    assert orig_db.estado == EstadoTurno.REPROGRAMADO.value
    assert orig_db.inicio == inicio_original

    # El nuevo turno apunta a turno_origen_id y está en pendiente
    assert nuevo_turno.turno_origen_id == turno_orig.id
    assert nuevo_turno.estado == EstadoTurno.PENDIENTE.value
    assert nuevo_turno.inicio == nuevo_inicio
    assert nuevo_token is not None

    # Fuera de término (< 24h antes del turno): canal público rechaza con 409 (RN-AG-05)
    ahora_tarde = nuevo_inicio - timedelta(hours=6)
    with pytest.raises(Conflicto) as exc_tarde:
        await cancelar_turno_publico(
            session,
            tenant_id=tenant.id,
            turno_id=nuevo_turno.id,
            motivo="No llego",
            ahora=ahora_tarde,
        )
    assert (
        "anticipación" in exc_tarde.value.mensaje.lower()
        or "término" in exc_tarde.value.mensaje.lower()
    )

    # Verificar que se escribieron registros en Auditoria (RN-SE-01)
    auditorias = (
        (await session.execute(select(Auditoria).where(Auditoria.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    acciones = {a.accion for a in auditorias}
    assert "turno.crear" in acciones
    assert "turno.reprogramar" in acciones
