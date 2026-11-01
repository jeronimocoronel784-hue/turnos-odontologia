"""Tests de reglas de negocio de Lista de Espera y Oferta de Huecos (tarea 2.1).

Verifica:
- RN-LE-01: orden por (prioridad ASC, created_at ASC), filtro de compatibilidad y salto de bajas.
- RN-LE-02: idempotencia por hueco/entrada y rotación al siguiente candidato al vencer ventana.
- RN-LE-03: colocación crea Turno vinculado; doble aceptación gana la primera y la segunda
  recibe ConflictoDisponibilidad con slots_alternativos.
- Integración con Agenda: cancelar un turno ofrece automáticamente el hueco liberado.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda import cambiar_estado_turno, crear_turno
from app.application.lista_espera import (
    aceptar_oferta_lista_espera,
    crear_entrada_lista_espera,
    dar_baja_lista_espera,
    ofrecer_hueco_lista_espera,
)
from app.domain.lista_espera import CanalAviso, EstadoListaEspera
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.passwords import hashear_password
from app.shared.exceptions import ConflictoDisponibilidad


async def _crear_contexto_le(
    session: AsyncSession,
    tenant: Tenant,
    sufijo: str = "1",
) -> tuple[list[Paciente], Usuario, Sillon, Prestacion]:
    pacientes: list[Paciente] = []
    for i in range(1, 4):
        p = Paciente(
            tenant_id=tenant.id,
            nombre=f"Paciente LE {sufijo}-{i}",
            dni=f"3500{sufijo}00{i}",
            telefono=f"+5491155550{sufijo}0{i}",
            optin_wa=True,
        )
        session.add(p)
        pacientes.append(p)

    odonto = Usuario(
        tenant_id=tenant.id,
        nombre=f"Dra. LE {sufijo}",
        email=f"odonto-le-{sufijo}@test.com",
        password_hash=hashear_password("Secret123!", rounds=4),
        rol=RolUsuario.ODONTOLOGO.value,
        matricula=f"MN-LE-{sufijo}",
        activo=True,
    )
    sillon = Sillon(
        tenant_id=tenant.id,
        nombre=f"Box LE {sufijo}",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        tenant_id=tenant.id,
        nombre=f"Limpieza LE {sufijo}",
        duracion_min=30,
        precio_particular=Decimal("18000.00"),
        requiere_sena=False,
        activa=True,
    )
    session.add_all([odonto, sillon, prestacion])
    await session.flush()
    return pacientes, odonto, sillon, prestacion


async def test_orden_prioridad_antiguedad_y_rotacion_ventana_vencida(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-LE-01/02: ordena por (prioridad, created_at), no duplica aviso y rota al vencer."""
    pacientes, odonto, sillon, prest = await _crear_contexto_le(session, tenant_a, "ord")
    t_base = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)

    # Entrada A: prioridad 1, creada a las 09:00
    e_a, _ = await crear_entrada_lista_espera(
        session,
        tenant_id=tenant_a.id,
        paciente_id=pacientes[0].id,
        prestacion_id=prest.id,
        prioridad=1,
        canal_aviso=CanalAviso.WA,
    )
    e_a.created_at = t_base + timedelta(hours=1)

    # Entrada B: prioridad 0 (urgente), creada a las 10:00 -> debe ir PRIMERA
    e_b, _ = await crear_entrada_lista_espera(
        session,
        tenant_id=tenant_a.id,
        paciente_id=pacientes[1].id,
        prestacion_id=prest.id,
        prioridad=0,
        canal_aviso=CanalAviso.WA,
    )
    e_b.created_at = t_base + timedelta(hours=2)

    # Entrada C: prioridad 1, creada a las 08:30 -> debe ir SEGUNDA (antes que A por antigüedad)
    e_c, _ = await crear_entrada_lista_espera(
        session,
        tenant_id=tenant_a.id,
        paciente_id=pacientes[2].id,
        prestacion_id=prest.id,
        prioridad=1,
        canal_aviso=CanalAviso.EMAIL,
    )
    e_c.created_at = t_base + timedelta(minutes=30)
    await session.flush()

    inicio_hueco = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    fin_hueco = inicio_hueco + timedelta(minutes=30)
    ahora_1 = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)

    # 1. Primer ofrecimiento elige a B (prioridad 0)
    avisada_1 = await ofrecer_hueco_lista_espera(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prest.id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        inicio=inicio_hueco,
        fin=fin_hueco,
        ventana_min=60,
        ahora=ahora_1,
    )
    assert avisada_1 is not None
    assert avisada_1.id == e_b.id
    assert avisada_1.estado == EstadoListaEspera.AVISADA.value
    assert avisada_1.ultimo_idempotency_key is not None

    # 2. Llamar de nuevo dentro de la ventana es idempotente: mantiene a B avisada sin duplicar
    avisada_idem = await ofrecer_hueco_lista_espera(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prest.id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        inicio=inicio_hueco,
        fin=fin_hueco,
        ventana_min=60,
        ahora=ahora_1 + timedelta(minutes=15),
    )
    assert avisada_idem is not None
    assert avisada_idem.id == e_b.id

    # 3. Vence la ventana de B (61 min) -> B vuelve a activa y se avisa a C (segunda en orden)
    ahora_vencida = ahora_1 + timedelta(minutes=61)
    avisada_2 = await ofrecer_hueco_lista_espera(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prest.id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        inicio=inicio_hueco,
        fin=fin_hueco,
        ventana_min=60,
        ahora=ahora_vencida,
    )
    assert avisada_2 is not None
    assert avisada_2.id == e_c.id
    assert e_b.estado == EstadoListaEspera.ACTIVA.value
    assert len(e_b.avisos_keys) == 1

    # 4. Si C se da de baja voluntariamente, la oferta pasa automáticamente a A (tercera en orden)
    await dar_baja_lista_espera(
        session,
        tenant_id=tenant_a.id,
        entrada_id=e_c.id,
        ahora=ahora_vencida + timedelta(minutes=5),
    )
    assert e_c.estado == EstadoListaEspera.BAJA.value
    assert e_a.estado == EstadoListaEspera.AVISADA.value


async def test_doble_aceptacion_simultanea_gana_primera_y_segunda_recibe_409_con_alternativas(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-LE-03 + Flujo 6: al aceptar se crea Turno y pasa a colocada; slot ocupado -> 409."""
    pacientes, odonto, sillon, prest = await _crear_contexto_le(session, tenant_a, "race")
    inicio_hueco = datetime(2026, 11, 21, 11, 0, tzinfo=UTC)
    fin_hueco = inicio_hueco + timedelta(minutes=30)
    ahora = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)

    e1, _ = await crear_entrada_lista_espera(
        session,
        tenant_id=tenant_a.id,
        paciente_id=pacientes[0].id,
        prestacion_id=prest.id,
        prioridad=0,
    )
    e2, _ = await crear_entrada_lista_espera(
        session,
        tenant_id=tenant_a.id,
        paciente_id=pacientes[1].id,
        prestacion_id=prest.id,
        prioridad=1,
    )

    await ofrecer_hueco_lista_espera(
        session,
        tenant_id=tenant_a.id,
        prestacion_id=prest.id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        inicio=inicio_hueco,
        fin=fin_hueco,
        ventana_min=60,
        ahora=ahora,
    )

    # Simulamos carrera: e2 también tenía el mismo hueco en estado avisada al mismo instante
    e2.estado = EstadoListaEspera.AVISADA.value
    e2.hueco_inicio = inicio_hueco
    e2.hueco_fin = fin_hueco
    e2.hueco_profesional_id = odonto.id
    e2.hueco_sillon_id = sillon.id
    e2.aviso_vence_at = ahora + timedelta(minutes=60)
    await session.flush()

    # 1. Primera aceptación (e1) gana: crea Turno y marca e1 colocada
    turno_creado, token_turno = await aceptar_oferta_lista_espera(
        session,
        tenant_id=tenant_a.id,
        entrada_id=e1.id,
        ahora=ahora + timedelta(minutes=5),
    )
    assert turno_creado.id is not None
    assert token_turno
    assert e1.estado == EstadoListaEspera.COLOCADA.value
    assert e1.turno_colocado_id == turno_creado.id

    # 2. Segunda aceptación simultánea (e2) choca con el turno recién creado -> 409 + alternativas
    with pytest.raises(ConflictoDisponibilidad) as exc_info:
        await aceptar_oferta_lista_espera(
            session,
            tenant_id=tenant_a.id,
            entrada_id=e2.id,
            ahora=ahora + timedelta(minutes=5),
        )
    assert len(exc_info.value.slots_alternativos) > 0


async def test_cancelar_turno_en_agenda_ofrece_hueco_a_lista_espera(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Flujo 6: cancelar un turno libera el slot y avisa a la primera entrada activa compatible."""
    pacientes, odonto, sillon, prest = await _crear_contexto_le(session, tenant_a, "hook")
    inicio_turno = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)

    turno, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=pacientes[0].id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        prestacion_id=prest.id,
        inicio=inicio_turno,
    )

    entrada_espera, _ = await crear_entrada_lista_espera(
        session,
        tenant_id=tenant_a.id,
        paciente_id=pacientes[1].id,
        prestacion_id=prest.id,
        profesional_id=odonto.id,
        prioridad=0,
    )
    assert entrada_espera.estado == EstadoListaEspera.ACTIVA.value

    # Cancelar el turno dispara la oferta automática a la lista de espera
    await cambiar_estado_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.CANCELADO,
        motivo_cancelacion="Viaje imprevisto",
    )
    await session.refresh(entrada_espera)
    assert entrada_espera.estado == EstadoListaEspera.AVISADA.value
    assert entrada_espera.hueco_profesional_id == odonto.id
    assert entrada_espera.hueco_sillon_id == sillon.id
