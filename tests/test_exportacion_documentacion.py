"""Contrato documentado de la exportación de datasets (C-14, tarea 4.8)."""

from app.main import app


def _operacion() -> dict:
    return app.openapi()["paths"]["/api/exportacion/{dataset}"]["get"]


def test_exportacion_endpoint_existe_en_openapi() -> None:
    assert "/api/exportacion/{dataset}" in app.openapi().get("paths", {})


def test_dataset_enum_documentado() -> None:
    params = {p.get("name"): p for p in _operacion().get("parameters", [])}
    assert "dataset" in params
    assert params["dataset"].get("schema", {}).get("enum") == [
        "agenda",
        "pacientes",
        "caja",
        "liquidaciones",
    ]


def test_formato_documentado() -> None:
    params = {p.get("name"): p for p in _operacion().get("parameters", [])}
    assert "formato" in params
    assert set(params["formato"].get("schema", {}).get("enum", [])) == {"csv", "json"}


def test_parametros_de_fecha_documentados() -> None:
    params = {p.get("name") for p in _operacion().get("parameters", [])}
    assert {"desde", "hasta"}.issubset(params)


def test_respuestas_documentadas() -> None:
    responses = _operacion().get("responses", {})
    for codigo in ("200", "202", "400", "403", "422", "503"):
        assert codigo in responses, f"Falta respuesta {codigo}"
