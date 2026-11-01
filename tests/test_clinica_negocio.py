"""Tests de integración de lógica de negocio para HC, Odontograma FDI y Consentimientos (tarea 2.1).

Verifica:
1. Edición de FichaClinica genera Evolucion + Auditoria sin PHI (RN-CL-01, R7, R9).
2. Odontograma FDI proyecta estado actual por pieza/superficie y conserva historial (RN-CL-01).
3. Prestación invasiva bloquea transición a 'presente' sin consentimiento firmado (RN-CL-02).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_clinica import (
    AdjuntoCreate,
    ConsentimientoCreate,
    ConsentimientoFirmaInput,
    EvolucionCreate,
    FichaClinicaUpdate,
    PiezaEventoCreate,
)
from app.application.agenda import cambiar_estado_turno, crear_turno
from app.application.clinica import (
    actualizar_ficha_clinica,
    crear_adjunto_clinico,
    crear_consentimiento,
    crear_evolucion,
    firmar_consentimiento_por_token,
    listar_evoluciones_paciente,
    listar_historial_pieza,
    obtener_odontograma_paciente,
    registrar_evento_pieza,
    revocar_consentimiento,
)
from app.domain.auditoria import Auditoria
from app.domain.clinica import (
    CanalFirmaConsentimiento,
    SuperficieDental,
    TipoAdjunto,
    TipoEventoPieza,
)
from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno
from app.domain.usuario import RolUsuario, Usuario
from app.shared.exceptions import Conflicto


async def _preparar_contexto_clinico(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[Usuario, Paciente, FichaClinica, Sillon, Prestacion]:
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="odontologo-hc@consultorio.test",
        nombre="Dr. Martín Odontólogo",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-54321",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        nombre="Lucía Paciente",
        dni="33444555",
        telefono="+5491166667777",
        optin_wa=True,
        activo=True,
    )
    session.add_all([odontologo, paciente])
    await session.flush()

    ficha = FichaClinica(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=paciente.id,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        nombre="Box Clínico 1",
        activo=True,
    )
    prestacion_inv = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        nombre="Endodoncia Unirradicular",
        duracion_min=60,
        precio_particular=Decimal("65000.00"),
        requiere_sena=False,
        invasiva=True,
        activa=True,
    )
    session.add_all([ficha, sillon, prestacion_inv])
    await session.flush()
    return odontologo, paciente, ficha, sillon, prestacion_inv


async def test_ficha_clinica_edicion_genera_evolucion_y_correccion_aditiva(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-CL-01, R7, R9: actualizar ficha crea Evolucion + Auditoria sin PHI; enmienda aditiva."""
    odontologo, paciente, ficha, _, _ = await _preparar_contexto_clinico(session, tenant_a.id)

    ficha_act = await actualizar_ficha_clinica(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        datos=FichaClinicaUpdate(
            alergias="Alergia severa a penicilina",
            antecedentes="Asma leve",
        ),
        actor_id=odontologo.id,
    )
    assert ficha_act.alergias == "Alergia severa a penicilina"

    evoluciones = await listar_evoluciones_paciente(
        session, tenant_id=tenant_a.id, paciente_id=paciente.id
    )
    assert len(evoluciones) == 1
    assert "anamnesis" in evoluciones[0].nota.lower()

    # Registrar evolución clínica y luego una corrección aditiva
    ev_orig = await crear_evolucion(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        datos=EvolucionCreate(nota="Se realiza apertura cameral pieza 24."),
        actor_id=odontologo.id,
    )
    ev_enmienda = await crear_evolucion(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        datos=EvolucionCreate(
            nota="Corrección: la apertura cameral fue en pieza 25.",
            es_correccion_de_id=ev_orig.id,
        ),
        actor_id=odontologo.id,
    )
    assert ev_enmienda.es_correccion_de_id == ev_orig.id
    assert ev_orig.nota == "Se realiza apertura cameral pieza 24."

    # Registrar adjunto clínico vinculado
    adj = await crear_adjunto_clinico(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        datos=AdjuntoCreate(
            tipo=TipoAdjunto.RX,
            nombre_archivo="rx-conductometria-25.png",
            mime_type="image/png",
            tamano_bytes=95000,
            storage_key=f"tenants/{tenant_a.id}/rx-25.png",
            evolucion_id=ev_enmienda.id,
        ),
        actor_id=odontologo.id,
    )
    assert adj.evolucion_id == ev_enmienda.id

    # Verificar que en auditoría no se haya filtrado PHI sensible ("penicilina")
    auditorias = (
        (
            await session.execute(
                select(Auditoria).where(
                    Auditoria.tenant_id == tenant_a.id,
                    Auditoria.entidad == "ficha_clinica",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(auditorias) >= 1
    assert "penicilina" not in str(auditorias[0].despues).lower()


async def test_odontograma_fdi_proyeccion_e_historial_inmutable(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-CL-01: eventos sucesivos en pieza/superficie proyectan estado y conservan historial."""
    odontologo, paciente, _, _, _ = await _preparar_contexto_clinico(session, tenant_a.id)

    ev1 = await registrar_evento_pieza(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        datos=PiezaEventoCreate(
            pieza_fdi=16,
            superficie=SuperficieDental.OCLUSAL,
            evento=TipoEventoPieza.CARIES,
            observacion="Lesión cavitada oclusal",
        ),
        actor_id=odontologo.id,
    )
    ev2 = await registrar_evento_pieza(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        datos=PiezaEventoCreate(
            pieza_fdi=16,
            superficie=SuperficieDental.OCLUSAL,
            evento=TipoEventoPieza.OBTURACION,
            observacion="Restauración con resina compuesta",
        ),
        actor_id=odontologo.id,
    )
    assert ev1.id != ev2.id

    odo = await obtener_odontograma_paciente(
        session, tenant_id=tenant_a.id, paciente_id=paciente.id
    )
    piezas_map = {p.pieza_fdi: p for p in odo.piezas}
    assert 16 in piezas_map
    assert piezas_map[16].superficies["oclusal"] == TipoEventoPieza.OBTURACION.value

    historial_16 = await listar_historial_pieza(
        session, tenant_id=tenant_a.id, paciente_id=paciente.id, pieza_fdi=16
    )
    assert [e.evento for e in historial_16] == [
        TipoEventoPieza.CARIES.value,
        TipoEventoPieza.OBTURACION.value,
    ]


async def test_consentimiento_bloquea_presente_en_invasiva_hasta_firmar(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-CL-02: turno invasivo bloquea transición a 'presente' sin consentimiento firmado."""
    odontologo, paciente, _, sillon, prestacion_inv = await _preparar_contexto_clinico(
        session, tenant_a.id
    )

    inicio = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
    turno, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion_inv.id,
        inicio=inicio,
        actor_id=odontologo.id,
    )
    await cambiar_estado_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.CONFIRMADO,
        actor_id=odontologo.id,
    )

    # 1. Intentar pasar a PRESENTE sin consentimiento -> 409 Conflicto
    with pytest.raises(Conflicto, match="consentimiento"):
        await cambiar_estado_turno(
            session,
            tenant_id=tenant_a.id,
            turno_id=turno.id,
            nuevo_estado=EstadoTurno.PRESENTE,
            actor_id=odontologo.id,
        )

    # 2. Emitir consentimiento con token público y firmarlo por token
    cons, token_firma = await crear_consentimiento(
        session,
        tenant_id=tenant_a.id,
        datos=ConsentimientoCreate(
            paciente_id=paciente.id,
            prestacion_id=prestacion_inv.id,
            turno_id=turno.id,
            texto_version="v1.0-endo",
            texto_contenido="Autorizo tratamiento de endodoncia.",
        ),
        actor_id=odontologo.id,
    )
    assert cons.firmado_at is None
    assert len(token_firma) > 16

    cons_firmado = await firmar_consentimiento_por_token(
        session,
        token=token_firma,
        datos=ConsentimientoFirmaInput(
            firmado_por="Lucía Paciente DNI 33444555",
            firma_datos="trazo-firma-digital-xyz",
            canal=CanalFirmaConsentimiento.TOKEN,
        ),
    )
    assert cons_firmado.firmado_at is not None
    assert cons_firmado.firma_hash is not None
    assert cons_firmado.canal == CanalFirmaConsentimiento.TOKEN.value

    # 3. Ahora el turno pasa a PRESENTE sin error
    turno_presente = await cambiar_estado_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno.id,
        nuevo_estado=EstadoTurno.PRESENTE,
        actor_id=odontologo.id,
    )
    assert turno_presente.estado == EstadoTurno.PRESENTE.value

    # 4. Revocar el consentimiento y verificar que un segundo turno invasivo quede bloqueado
    await revocar_consentimiento(
        session,
        tenant_id=tenant_a.id,
        consentimiento_id=cons.id,
        motivo="Paciente solicita revocación para el próximo turno",
        actor_id=odontologo.id,
    )
    turno2, _ = await crear_turno(
        session,
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion_inv.id,
        inicio=datetime(2026, 11, 26, 14, 0, tzinfo=UTC),
        actor_id=odontologo.id,
    )
    await cambiar_estado_turno(
        session,
        tenant_id=tenant_a.id,
        turno_id=turno2.id,
        nuevo_estado=EstadoTurno.CONFIRMADO,
        actor_id=odontologo.id,
    )
    with pytest.raises(Conflicto, match="consentimiento"):
        await cambiar_estado_turno(
            session,
            tenant_id=tenant_a.id,
            turno_id=turno2.id,
            nuevo_estado=EstadoTurno.PRESENTE,
            actor_id=odontologo.id,
        )
