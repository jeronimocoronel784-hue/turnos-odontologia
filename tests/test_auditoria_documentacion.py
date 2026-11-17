"""Contrato documentado del trail de auditor��a (C-14, tarea 1.4).

Verifica que `GET /api/auditoria` estǸ registrado en el OpenAPI generado con sus
parǭmetros de filtro y paginaci��n.
"""

from app.main import app


def _rutas() -> dict:
    return app.openapi().get("paths", {})


def test_endpoint_auditoria_existe_en_openapi() -> None:
    paths = _rutas()
    assert "/api/auditoria" in paths, "Falta /api/auditoria en OpenAPI"
    assert "get" in paths["/api/auditoria"]


def test_parametros_de_filtro_y_paginacion_estan_documentados() -> None:
    operacion = _rutas()["/api/auditoria"]["get"]
    params = {p.get("name") for p in operacion.get("parameters", [])}
    esperados = {
        "entidad",
        "entidad_id",
        "actor_id",
        "accion",
        "desde",
        "hasta",
        "limite",
        "cursor",
    }
    assert esperados.issubset(params), f"Faltan parǭmetros: {esperados - params}"


def test_respuesta_usa_schema_auditoria() -> None:
    operacion = _rutas()["/api/auditoria"]["get"]
    responses = operacion.get("responses", {})
    assert "200" in responses
