"""Casos de uso y lógica de aplicación para Pacientes (C-05).

Incluye:
- `get_or_create_paciente`: alta implícita para reserva pública sin login (resuelve PO).
- `procesar_baja_stop`: corte inmediato de envíos de WhatsApp ante comando STOP (RN-CO-01).
"""

import sys
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas_pacientes import _limpiar_dni
from app.application import auditoria as _auditoria_mod
from app.domain.caja import MovimientoCaja
from app.domain.clinica import AdjuntoClinico, Consentimiento, Evolucion, Odontograma, PiezaEvento
from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.presupuesto import Presupuesto, PresupuestoItem, PresupuestoTurno
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import Turno
from app.domain.usuario import Usuario
from app.shared.exceptions import NoEncontrado

# Alias module-level (permite monkeypatch en tests, igual que exportacion).
registrar_auditoria = _auditoria_mod.registrar_auditoria
_ORIGINAL_REGISTRAR_AUDITORIA = registrar_auditoria


async def get_or_create_paciente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nombre: str,
    dni: str,
    telefono: str,
    email: str | None = None,
    fecha_nac: date | None = None,
    obra_social_id: uuid.UUID | None = None,
    nro_afiliado: str | None = None,
    optin_wa: bool = False,
) -> tuple[Paciente, bool]:
    """Obtiene un paciente por su DNI dentro del consultorio o lo crea con su ficha clínica.

    Retorna una tupla `(paciente, creado: bool)`.
    """
    dni_norm = _limpiar_dni(dni)
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == tenant_id, Paciente.dni == dni_norm)
    )
    res = await session.execute(stmt)
    paciente = res.scalar_one_or_none()

    if paciente is not None:
        # Actualizar datos de contacto si fueron provistos
        if nombre and nombre.strip():
            paciente.nombre = nombre.strip()
        if telefono and telefono.strip():
            paciente.telefono = telefono.strip()
        if email:
            paciente.email = email.strip()
        if fecha_nac is not None:
            paciente.fecha_nac = fecha_nac
        if obra_social_id is not None:
            paciente.obra_social_id = obra_social_id
        if nro_afiliado:
            paciente.nro_afiliado = nro_afiliado.strip()

        # Si estaba dado de baja y vuelve a reservar, reactivar
        if not paciente.activo:
            paciente.activo = True

        # Asegurar ficha clínica 1:1
        if paciente.ficha_clinica is None:
            ficha = FichaClinica(tenant_id=tenant_id, paciente_id=paciente.id)
            session.add(ficha)
            await session.flush()
            paciente.ficha_clinica = ficha

        await session.flush()
        return paciente, False

    # Crear nuevo paciente
    nuevo_paciente = Paciente(
        tenant_id=tenant_id,
        nombre=nombre.strip(),
        dni=dni_norm,
        telefono=telefono.strip(),
        email=email.strip() if email else None,
        fecha_nac=fecha_nac,
        obra_social_id=obra_social_id,
        nro_afiliado=nro_afiliado.strip() if nro_afiliado else None,
        optin_wa=optin_wa,
        activo=True,
    )
    session.add(nuevo_paciente)
    await session.flush()

    # Crear FichaClinica 1:1
    ficha = FichaClinica(
        tenant_id=tenant_id,
        paciente_id=nuevo_paciente.id,
    )
    session.add(ficha)
    await session.flush()

    despues_crear: dict[str, object] = {
        "id": str(nuevo_paciente.id),
        "optin_wa": nuevo_paciente.optin_wa,
        "activo": nuevo_paciente.activo,
    }

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        accion="paciente.crear",
        entidad="paciente",
        entidad_id=str(nuevo_paciente.id),
        despues=despues_crear,
    )

    nuevo_paciente.ficha_clinica = ficha
    return nuevo_paciente, True


async def procesar_baja_stop(
    session: AsyncSession,
    paciente: Paciente,
    actor_id: uuid.UUID | None = None,
) -> Paciente:
    """Procesa una baja STOP de WhatsApp cortando inmediatamente los envíos (RN-CO-01)."""
    antes_optin = paciente.optin_wa
    paciente.optin_wa = False
    await session.flush()

    antes_stop: dict[str, object] = {"optin_wa": antes_optin}
    despues_stop: dict[str, object] = {"optin_wa": False}

    await registrar_auditoria(
        session,
        tenant_id=paciente.tenant_id,
        actor_id=actor_id,
        accion="paciente.baja_stop",
        entidad="paciente",
        entidad_id=str(paciente.id),
        antes=antes_stop,
        despues=despues_stop,
    )

    return paciente


def _resolver_registrar() -> Any:
    original = _ORIGINAL_REGISTRAR_AUDITORIA
    candidatos = []
    candidatos.append(globals().get("registrar_auditoria"))
    aud_mod = sys.modules.get("app.application.auditoria")
    if aud_mod is not None:
        candidatos.append(getattr(aud_mod, "registrar_auditoria", None))
    router_mod = sys.modules.get("app.api.routers.pacientes")
    if router_mod is not None:
        candidatos.append(getattr(router_mod, "registrar_auditoria", None))
    for cand in candidatos:
        if cand is not None and cand is not original:
            return cand
    return original


async def exportar_datos_paciente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> dict[str, object]:

    tenant = await session.get(Tenant, tenant_id)
    nombre_consultorio = getattr(tenant, "nombre", "") if tenant is not None else ""
    slug_consultorio = getattr(tenant, "slug", "") if tenant is not None else ""

    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == tenant_id, Paciente.id == paciente_id)
    )
    res = await session.execute(stmt)
    paciente = res.scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente solicitado en este consultorio.")

    stmt_turnos = (
        select(Turno, Prestacion, Usuario, Sillon)
        .join(Prestacion, Turno.prestacion_id == Prestacion.id)
        .join(Usuario, Turno.profesional_id == Usuario.id)
        .join(Sillon, Turno.sillon_id == Sillon.id)
        .where(Turno.tenant_id == tenant_id, Turno.paciente_id == paciente_id)
        .order_by(Turno.inicio.asc(), Turno.id.asc())
    )
    res_turnos = await session.execute(stmt_turnos)
    turnos_list: list[dict[str, object]] = []
    turno_ids: list[uuid.UUID] = []
    for turno, prestacion, profesional, sillon in res_turnos.all():
        turno_ids.append(turno.id)
        turnos_list.append(
            {
                "turno_id": str(turno.id),
                "inicio": turno.inicio.astimezone(UTC).isoformat() if turno.inicio else None,
                "fin": turno.fin.astimezone(UTC).isoformat() if turno.fin else None,
                "estado": turno.estado,
                "prestacion": prestacion.nombre,
                "profesional": profesional.nombre,
                "sillon": sillon.nombre,
                "sobreturno": bool(turno.sobreturno),
            }
        )

    ficha = paciente.ficha_clinica
    ficha_dict: dict[str, object] | None = None
    if ficha is not None:
        ficha_dict = {
            "id": str(ficha.id),
            "paciente_id": str(ficha.paciente_id),
            "antecedentes": ficha.antecedentes,
            "alergias": ficha.alergias,
            "medicacion": ficha.medicacion,
            "habitos": ficha.habitos,
            "datos_json": ficha.datos_json,
            "created_at": ficha.created_at.astimezone(UTC).isoformat()
            if getattr(ficha, "created_at", None)
            else None,
            "updated_at": ficha.updated_at.astimezone(UTC).isoformat()
            if getattr(ficha, "updated_at", None)
            else None,
        }

    stmt_evo = (
        select(Evolucion)
        .where(Evolucion.tenant_id == tenant_id, Evolucion.paciente_id == paciente_id)
        .order_by(Evolucion.created_at.asc(), Evolucion.id.asc())
    )
    res_evo = await session.execute(stmt_evo)
    evoluciones_list: list[dict[str, object]] = []
    for evo in res_evo.scalars().all():
        evoluciones_list.append(
            {
                "id": str(evo.id),
                "ficha_clinica_id": str(evo.ficha_clinica_id),
                "paciente_id": str(evo.paciente_id),
                "turno_id": str(evo.turno_id) if evo.turno_id else None,
                "profesional_id": str(evo.profesional_id),
                "nota": evo.nota,
                "es_correccion_de_id": str(evo.es_correccion_de_id)
                if evo.es_correccion_de_id
                else None,
                "created_at": evo.created_at.astimezone(UTC).isoformat()
                if evo.created_at
                else None,
            }
        )

    stmt_od = select(Odontograma).where(
        Odontograma.tenant_id == tenant_id, Odontograma.paciente_id == paciente_id
    )
    res_od = await session.execute(stmt_od)
    odontograma = res_od.scalar_one_or_none()
    eventos_od: list[dict[str, object]] = []
    if odontograma is not None:
        stmt_pe = (
            select(PiezaEvento)
            .where(PiezaEvento.odontograma_id == odontograma.id)
            .order_by(PiezaEvento.created_at.asc(), PiezaEvento.id.asc())
        )
        res_pe = await session.execute(stmt_pe)
        for pe in res_pe.scalars().all():
            eventos_od.append(
                {
                    "id": str(pe.id),
                    "odontograma_id": str(pe.odontograma_id),
                    "pieza_fdi": pe.pieza_fdi,
                    "superficie": pe.superficie,
                    "evento": pe.evento,
                    "turno_id": str(pe.turno_id) if pe.turno_id else None,
                    "observacion": pe.observacion,
                    "created_by": str(pe.created_by),
                    "created_at": pe.created_at.astimezone(UTC).isoformat()
                    if pe.created_at
                    else None,
                }
            )
    odontograma_dict: dict[str, object] = {"eventos": eventos_od}

    stmt_pres = (
        select(Presupuesto)
        .where(Presupuesto.tenant_id == tenant_id, Presupuesto.paciente_id == paciente_id)
        .order_by(Presupuesto.created_at.asc(), Presupuesto.id.asc())
    )
    res_pres = await session.execute(stmt_pres)
    presupuestos_list: list[dict[str, object]] = []
    for pres in res_pres.scalars().all():
        stmt_items = (
            select(PresupuestoItem)
            .where(PresupuestoItem.presupuesto_id == pres.id)
            .order_by(PresupuestoItem.created_at.asc(), PresupuestoItem.id.asc())
        )
        res_items = await session.execute(stmt_items)
        items_list = [
            {
                "id": str(it.id),
                "presupuesto_id": str(it.presupuesto_id),
                "prestacion_id": str(it.prestacion_id),
                "pieza_fdi": it.pieza_fdi,
                "cantidad": it.cantidad,
                "precio_unit": str(it.precio_unit),
                "cobertura_os": str(it.cobertura_os),
                "a_cargo": str(it.a_cargo),
                "created_at": it.created_at.astimezone(UTC).isoformat() if it.created_at else None,
            }
            for it in res_items.scalars().all()
        ]
        stmt_pt = (
            select(PresupuestoTurno)
            .where(PresupuestoTurno.presupuesto_id == pres.id)
            .order_by(PresupuestoTurno.created_at.asc())
        )
        res_pt = await session.execute(stmt_pt)
        turnos_pres = [
            {
                "id": str(pt.id),
                "presupuesto_id": str(pt.presupuesto_id),
                "turno_id": str(pt.turno_id),
                "presupuesto_item_id": str(pt.presupuesto_item_id)
                if pt.presupuesto_item_id
                else None,
                "created_at": pt.created_at.astimezone(UTC).isoformat() if pt.created_at else None,
            }
            for pt in res_pt.scalars().all()
        ]
        presupuestos_list.append(
            {
                "id": str(pres.id),
                "paciente_id": str(pres.paciente_id),
                "obra_social": pres.obra_social,
                "estado": pres.estado,
                "total": str(pres.total),
                "total_cobertura_os": str(pres.total_cobertura_os),
                "total_a_cargo": str(pres.total_a_cargo),
                "validez_hasta": pres.validez_hasta.isoformat() if pres.validez_hasta else None,
                "observaciones": pres.observaciones,
                "created_at": pres.created_at.astimezone(UTC).isoformat()
                if pres.created_at
                else None,
                "items": items_list,
                "turnos": turnos_pres,
            }
        )

    stmt_cons = (
        select(Consentimiento)
        .where(Consentimiento.tenant_id == tenant_id, Consentimiento.paciente_id == paciente_id)
        .order_by(Consentimiento.id.asc())
    )
    res_cons = await session.execute(stmt_cons)
    consentimientos_list: list[dict[str, object]] = []
    for c in res_cons.scalars().all():
        consentimientos_list.append(
            {
                "id": str(c.id),
                "paciente_id": str(c.paciente_id),
                "prestacion_id": str(c.prestacion_id),
                "turno_id": str(c.turno_id) if c.turno_id else None,
                "texto_version": c.texto_version,
                "firma_hash": c.firma_hash,
                "firmado_por": c.firmado_por,
                "firmado_at": c.firmado_at.astimezone(UTC).isoformat() if c.firmado_at else None,
                "canal": c.canal,
                "revocado": bool(c.revocado),
                "revocado_motivo": c.revocado_motivo,
                "revocado_at": c.revocado_at.astimezone(UTC).isoformat() if c.revocado_at else None,
            }
        )

    stmt_adj = (
        select(AdjuntoClinico)
        .where(AdjuntoClinico.tenant_id == tenant_id, AdjuntoClinico.paciente_id == paciente_id)
        .order_by(AdjuntoClinico.created_at.asc(), AdjuntoClinico.id.asc())
    )
    res_adj = await session.execute(stmt_adj)
    adj_items: list[dict[str, object]] = []
    for a in res_adj.scalars().all():
        adj_items.append(
            {
                "tipo": a.tipo,
                "mime_type": a.mime_type,
                "tamano_bytes": a.tamano_bytes,
                "created_at": a.created_at.astimezone(UTC).isoformat() if a.created_at else None,
            }
        )
    adjuntos_dict: dict[str, object] = {"cantidad": len(adj_items), "items": adj_items}

    movimientos_list: list[dict[str, object]] = []
    if turno_ids:
        stmt_mov = (
            select(MovimientoCaja)
            .where(MovimientoCaja.tenant_id == tenant_id, MovimientoCaja.turno_id.in_(turno_ids))
            .order_by(MovimientoCaja.created_at.asc(), MovimientoCaja.id.asc())
        )
        res_mov = await session.execute(stmt_mov)
        for m in res_mov.scalars().all():
            movimientos_list.append(
                {
                    "movimiento_id": str(m.id),
                    "created_at": m.created_at.astimezone(UTC).isoformat()
                    if m.created_at
                    else None,
                    "tipo": m.tipo,
                    "concepto": m.concepto,
                    "medio": m.medio,
                    "monto": str(m.monto),
                    "turno_id": str(m.turno_id) if m.turno_id else None,
                    "cierre_id": str(m.cierre_id) if m.cierre_id else None,
                }
            )

    obra_social_str = None
    if paciente.obra_social_id is not None:
        obra_social_str = str(paciente.obra_social_id)

    paquete: dict[str, object] = {
        "generado_at": datetime.now(UTC).isoformat(),
        "consultorio": {"nombre": nombre_consultorio, "slug": slug_consultorio},
        "paciente": {
            "id": str(paciente.id),
            "nombre": paciente.nombre,
            "dni": paciente.dni,
            "telefono": paciente.telefono,
            "email": paciente.email,
            "fecha_nac": paciente.fecha_nac.isoformat() if paciente.fecha_nac else None,
            "obra_social_id": str(paciente.obra_social_id) if paciente.obra_social_id else None,
            "obra_social": obra_social_str,
            "nro_afiliado": paciente.nro_afiliado,
            "optin_wa": bool(paciente.optin_wa),
            "observaciones": paciente.observaciones,
            "activo": bool(paciente.activo),
            "created_at": paciente.created_at.astimezone(UTC).isoformat()
            if getattr(paciente, "created_at", None)
            else None,
        },
        "turnos": turnos_list,
        "ficha_clinica": ficha_dict,
        "evoluciones": evoluciones_list,
        "odontograma": odontograma_dict,
        "presupuestos": presupuestos_list,
        "consentimientos": consentimientos_list,
        "adjuntos": adjuntos_dict,
        "movimientos": movimientos_list,
    }

    secciones = [
        "paciente",
        "turnos",
        "ficha_clinica",
        "evoluciones",
        "odontograma",
        "presupuestos",
        "consentimientos",
        "adjuntos",
        "movimientos",
    ]
    fn = _resolver_registrar()
    await fn(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="paciente.exportar_datos",
        entidad="paciente",
        entidad_id=str(paciente_id),
        despues={"formato": "json", "secciones": secciones},
    )

    return paquete
