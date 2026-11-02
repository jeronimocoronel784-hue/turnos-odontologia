"""Tests unitarios de schemas Pydantic v2 para señas, caja y cierres (tarea 1.2).

Verifica:
1. R1: `extra='forbid'` en todos los inputs (no se puede inyectar `tenant_id`, `monto`, `estado`).
2. R8: ningún input acepta montos que calcula el servidor (seña, saldo del turno).
3. Enums cerrados (`MedioPago`, `TipoMovimientoCaja`) y montos `Decimal` positivos con 2 decimales.
4. Modelos de lectura explícitos con `from_attributes` (nunca se expone el ORM, R1).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.schemas_caja import (
    CierreCajaAbrirInput,
    CierreCajaCerrarInput,
    CierreCajaReabrirInput,
    CierreCajaRead,
    CobrarTurnoInput,
    LiquidacionTurnoRead,
    MovimientoCajaCreate,
    MovimientoCajaRead,
    SenaCobrarInput,
    SenaCreate,
    SenaRead,
    SenaResolverCancelacionInput,
)
from app.domain.caja import EstadoCierreCaja, EstadoSena, MedioPago, TipoMovimientoCaja


def test_sena_create_exige_turno_y_bloquea_monto_y_estado_del_cliente() -> None:
    """R1/R8: la seña manual solo recibe el turno; monto y estado los fija el servidor."""
    turno_id = uuid.uuid4()
    sena_ok = SenaCreate(turno_id=turno_id)
    assert sena_ok.turno_id == turno_id
    assert sena_ok.vence_at is None

    with pytest.raises(ValidationError):
        SenaCreate()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        SenaCreate(turno_id=turno_id, monto=Decimal("10000.00"))  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        SenaCreate(turno_id=turno_id, estado="cobrada")  # type: ignore[call-arg]

    # `vence_at` (si se informa) exige zona horaria explícita.
    aware = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    assert SenaCreate(turno_id=turno_id, vence_at=aware).vence_at == aware
    with pytest.raises(ValidationError):
        SenaCreate(turno_id=turno_id, vence_at=datetime(2026, 11, 2, 12, 0))


def test_sena_cobrar_input_solo_recibe_medio_de_pago() -> None:
    """R8: el cobro de la seña no acepta monto; el importe sale de la seña persistida."""
    cobro = SenaCobrarInput(medio="efectivo")
    assert cobro.medio is MedioPago.EFECTIVO

    with pytest.raises(ValidationError):
        SenaCobrarInput(medio="cheque")
    with pytest.raises(ValidationError):
        SenaCobrarInput()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SenaCobrarInput(medio="efectivo", monto=Decimal("10000.00"))  # type: ignore[call-arg]


def test_sena_resolver_cancelacion_normaliza_motivo_y_detecta_ausente() -> None:
    """RN-PA-04: `ausente` distingue retención de devolución y el motivo va normalizado."""
    resolucion = SenaResolverCancelacionInput()
    assert resolucion.ausente is False
    assert resolucion.motivo is None

    con_motivo = SenaResolverCancelacionInput(ausente=True, motivo="  No asistió  ")
    assert con_motivo.ausente is True
    assert con_motivo.motivo == "No asistió"

    with pytest.raises(ValidationError):
        SenaResolverCancelacionInput(motivo="x" * 501)
    with pytest.raises(ValidationError):
        SenaResolverCancelacionInput(estado="devuelta")  # type: ignore[call-arg]

    # Motivo opcional en blanco: se normaliza a `None` (misma convención que `TurnoEstadoUpdate`).
    assert SenaResolverCancelacionInput(motivo="   ").motivo is None


def test_movimiento_caja_create_valida_monto_positivo_enums_y_concepto() -> None:
    """R1/R8: monto `Decimal` > 0 con 2 decimales, tipo/medio del enum y concepto no vacío."""
    movimiento = MovimientoCajaCreate(
        tipo=TipoMovimientoCaja.EGRESO,
        concepto="  Compra de insumos  ",
        medio=MedioPago.TRANSFERENCIA,
        monto=Decimal("15000.50"),
        turno_id=uuid.uuid4(),
    )
    assert movimiento.tipo is TipoMovimientoCaja.EGRESO
    assert movimiento.medio is MedioPago.TRANSFERENCIA
    assert movimiento.concepto == "Compra de insumos"
    assert movimiento.monto == Decimal("15000.50")
    assert movimiento.sena_id is None

    base = {
        "tipo": "ingreso",
        "concepto": "Cobro de saldo",
        "medio": "debito",
        "monto": Decimal("20000.00"),
    }
    with pytest.raises(ValidationError):
        MovimientoCajaCreate(**{**base, "monto": Decimal("0.00")})
    with pytest.raises(ValidationError):
        MovimientoCajaCreate(**{**base, "monto": Decimal("-20000.00")})
    with pytest.raises(ValidationError):
        MovimientoCajaCreate(**{**base, "monto": Decimal("20000.999")})
    with pytest.raises(ValidationError):
        MovimientoCajaCreate(**{**base, "tipo": "transferencia"})
    with pytest.raises(ValidationError):
        MovimientoCajaCreate(**{**base, "medio": "cheque"})
    with pytest.raises(ValidationError):
        MovimientoCajaCreate(**{**base, "concepto": "   "})
    # D3: el cierre vigente lo asigna el servidor, no el cliente.
    with pytest.raises(ValidationError):
        MovimientoCajaCreate(**base, cierre_id=uuid.uuid4())


def test_cierre_caja_inputs_exigen_fecha_contado_y_motivo() -> None:
    """D3: abrir pide fecha, cerrar pide `total_contado` no negativo y reabrir pide motivo."""
    assert CierreCajaAbrirInput(fecha=date(2026, 11, 10)).fecha == date(2026, 11, 10)
    with pytest.raises(ValidationError):
        CierreCajaAbrirInput()  # type: ignore[call-arg]

    cierre = CierreCajaCerrarInput(total_contado=Decimal("29500.00"))
    assert cierre.total_contado == Decimal("29500.00")
    with pytest.raises(ValidationError):
        CierreCajaCerrarInput(total_contado=Decimal("-1.00"))
    with pytest.raises(ValidationError):
        CierreCajaCerrarInput(total_contado=Decimal("29500.001"))
    with pytest.raises(ValidationError):
        CierreCajaCerrarInput()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        CierreCajaCerrarInput(  # type: ignore[call-arg]
            total_contado=Decimal("29500.00"), total_sistema=Decimal("30000.00")
        )

    reabrir = CierreCajaReabrirInput(motivo="  Error de tipeo en el contado  ")
    assert reabrir.motivo == "Error de tipeo en el contado"
    with pytest.raises(ValidationError):
        CierreCajaReabrirInput(motivo="   ")
    with pytest.raises(ValidationError):
        CierreCajaReabrirInput(motivo="")
    with pytest.raises(ValidationError):
        CierreCajaReabrirInput()  # type: ignore[call-arg]


def test_cobrar_turno_input_no_acepta_saldo_calculado_por_el_cliente() -> None:
    """R8/Flujo 4: el saldo se calcula en servidor; el input solo elige medio y OS."""
    cobro = CobrarTurnoInput(medio=MedioPago.MP, obra_social="  OSDE  ")
    assert cobro.medio is MedioPago.MP
    assert cobro.obra_social == "OSDE"
    assert CobrarTurnoInput(medio="efectivo").obra_social is None

    with pytest.raises(ValidationError):
        CobrarTurnoInput(medio="efectivo", saldo=Decimal("20000.00"))  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        CobrarTurnoInput(medio="efectivo", monto=Decimal("20000.00"))  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        CobrarTurnoInput(medio="cheque")


def test_reads_mapean_desde_orm_y_rechazan_campos_extra() -> None:
    """R1: los modelos de lectura se arman desde atributos y no admiten extras."""
    tenant_id = uuid.uuid4()
    turno_id = uuid.uuid4()
    ahora = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    sena_orm = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        turno_id=turno_id,
        monto=Decimal("10000.00"),
        estado="cobrada",
        mp_payment_id=None,
        vence_at=None,
        created_at=ahora,
        updated_at=ahora,
    )
    sena = SenaRead.model_validate(sena_orm)
    assert sena.estado is EstadoSena.COBRADA
    assert sena.monto == Decimal("10000.00")
    with pytest.raises(ValidationError):
        SenaRead.model_validate({**vars(sena_orm), "saldo": Decimal("1.00")})

    movimiento_orm = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        tipo="egreso",
        concepto="Compra de insumos",
        medio="transferencia",
        monto=Decimal("15000.50"),
        turno_id=None,
        sena_id=None,
        cobro_mp_id=None,
        cierre_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        created_at=ahora,
    )
    movimiento = MovimientoCajaRead.model_validate(movimiento_orm)
    assert movimiento.tipo is TipoMovimientoCaja.EGRESO
    assert movimiento.medio is MedioPago.TRANSFERENCIA
    with pytest.raises(ValidationError):
        MovimientoCajaRead.model_validate({**vars(movimiento_orm), "estado": "cerrado"})

    cierre_orm = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        fecha=date(2026, 11, 10),
        total_sistema=Decimal("30000.00"),
        total_contado=Decimal("29500.00"),
        diferencia=Decimal("-500.00"),
        estado="cerrado",
        abierto_por=uuid.uuid4(),
        cerrado_por=uuid.uuid4(),
        cerrado_at=ahora,
        reabierto_motivo=None,
        created_at=ahora,
        updated_at=ahora,
    )
    cierre = CierreCajaRead.model_validate(cierre_orm)
    assert cierre.estado is EstadoCierreCaja.CERRADO
    assert cierre.diferencia == Decimal("-500.00")
    with pytest.raises(ValidationError):
        CierreCajaRead.model_validate({**vars(cierre_orm), "movimientos": []})

    liquidacion = LiquidacionTurnoRead(
        turno_id=turno_id,
        precio_particular=Decimal("50000.00"),
        cobertura_os=Decimal("20000.00"),
        sena_cobrada=Decimal("10000.00"),
        saldo=Decimal("20000.00"),
        obra_social="OSDE",
    )
    assert liquidacion.saldo == Decimal("20000.00")
    with pytest.raises(ValidationError):
        LiquidacionTurnoRead(
            turno_id=turno_id,
            precio_particular=Decimal("50000.00"),
            cobertura_os=Decimal("20000.00"),
            sena_cobrada=Decimal("10000.00"),
            saldo=Decimal("20000.00"),
            total=Decimal("50000.00"),  # type: ignore[call-arg]
        )
