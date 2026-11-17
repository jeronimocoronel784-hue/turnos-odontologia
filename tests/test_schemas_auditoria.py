"""Schemas de lectura del trail (C-14, tarea 1.2).

`AuditoriaEventoRead` no expone el ORM (`R1`) ni `tenant_id` (redundante: el filtro
sale del token, D2). `created_at` se normaliza a UTC porque SQLite devuelve naive
aunque la columna sea `timezone=True` (`app/domain/mixins.py`).
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.api.schemas_auditoria import AuditoriaEventoRead, AuditoriaPaginaRead

ART = timezone(timedelta(hours=-3), "America/Argentina/Buenos_Aires")


def _datos(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "actor_id": uuid.uuid4(),
        "accion": "turno.cambiar_estado",
        "entidad": "turno",
        "entidad_id": "turno-1",
        "antes": {"estado": "pendiente"},
        "despues": {"estado": "confirmado"},
        "created_at": datetime(2026, 11, 10, 14, 30, tzinfo=UTC),
    }
    base.update(cambios)
    return base


def test_evento_expone_los_campos_del_contrato_y_no_el_tenant() -> None:
    evento = AuditoriaEventoRead.model_validate(_datos(tenant_id=uuid.uuid4()))

    assert set(AuditoriaEventoRead.model_fields) == {
        "id",
        "actor_id",
        "accion",
        "entidad",
        "entidad_id",
        "antes",
        "despues",
        "created_at",
    }
    assert "tenant_id" not in evento.model_dump()


def test_evento_serializa_antes_y_despues_como_json() -> None:
    evento = AuditoriaEventoRead.model_validate(
        _datos(antes=None, despues={"detalles_liberados": 2, "motivo": "re-liquidar"})
    )

    volcado = evento.model_dump(mode="json")

    assert volcado["antes"] is None
    assert volcado["despues"] == {"detalles_liberados": 2, "motivo": "re-liquidar"}
    assert volcado["actor_id"] == str(evento.actor_id)


def test_evento_sin_actor_es_valido_para_eventos_del_sistema() -> None:
    evento = AuditoriaEventoRead.model_validate(_datos(actor_id=None))

    assert evento.actor_id is None
    assert evento.model_dump(mode="json")["actor_id"] is None


def test_created_at_naive_se_interpreta_utc() -> None:
    evento = AuditoriaEventoRead.model_validate(_datos(created_at=datetime(2026, 11, 10, 14, 30)))

    assert evento.created_at.utcoffset() == timedelta(0)
    assert evento.created_at.hour == 14


def test_created_at_con_otro_offset_se_normaliza_a_utc() -> None:
    evento = AuditoriaEventoRead.model_validate(
        _datos(created_at=datetime(2026, 11, 10, 11, 30, tzinfo=ART))
    )

    assert evento.created_at == datetime(2026, 11, 10, 14, 30, tzinfo=UTC)
    serializado = evento.model_dump(mode="json")["created_at"]
    assert serializado.endswith(("+00:00", "Z"))
    assert datetime.fromisoformat(serializado.replace("Z", "+00:00")) == datetime(
        2026, 11, 10, 14, 30, tzinfo=UTC
    )


def test_accion_y_entidad_son_obligatorias() -> None:
    datos = _datos()
    datos.pop("accion")

    with pytest.raises(ValidationError):
        AuditoriaEventoRead.model_validate(datos)


def test_pagina_por_defecto_no_tiene_siguiente_cursor() -> None:
    evento = AuditoriaEventoRead.model_validate(_datos())

    pagina = AuditoriaPaginaRead(eventos=[evento])

    assert pagina.siguiente_cursor is None
    assert pagina.model_dump(mode="json")["siguiente_cursor"] is None


def test_pagina_conserva_el_cursor_opaco_tal_cual() -> None:
    evento = AuditoriaEventoRead.model_validate(_datos())
    cursor = "MjAyNi0xMS0xMFQxNDozMDowMCswMDowMHx1dWlk"

    pagina = AuditoriaPaginaRead(eventos=[evento], siguiente_cursor=cursor)

    assert pagina.model_dump(mode="json") == {
        "eventos": [evento.model_dump(mode="json")],
        "siguiente_cursor": cursor,
    }
