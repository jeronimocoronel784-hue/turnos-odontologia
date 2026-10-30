"""Contrato documentado de catálogo y configuración coincide con las rutas reales (tarea 2.5).

Verifica:
- README.md documenta los endpoints de /api/admin para
  sillones, prestaciones, coberturas y tenant/politicas.
- Todas las rutas documentadas existen en `app.routes` de FastAPI con sus métodos HTTP correctos.
- README.md y CHANGES.md reflejan el estado del change C-04.
"""

from pathlib import Path

from app.main import app

RAIZ = Path(__file__).resolve().parents[1]
README = (RAIZ / "README.md").read_text(encoding="utf-8")
CHANGES = (RAIZ / "CHANGES.md").read_text(encoding="utf-8")

RUTAS_CATALOGO_ESPERADAS = [
    ("GET", "/api/admin/sillones"),
    ("POST", "/api/admin/sillones"),
    ("PATCH", "/api/admin/sillones/{sillon_id}"),
    ("DELETE", "/api/admin/sillones/{sillon_id}"),
    ("GET", "/api/admin/prestaciones"),
    ("POST", "/api/admin/prestaciones"),
    ("PATCH", "/api/admin/prestaciones/{prestacion_id}"),
    ("DELETE", "/api/admin/prestaciones/{prestacion_id}"),
    ("GET", "/api/admin/coberturas"),
    ("POST", "/api/admin/coberturas"),
    ("PATCH", "/api/admin/coberturas/{cobertura_id}"),
    ("DELETE", "/api/admin/coberturas/{cobertura_id}"),
    ("GET", "/api/admin/tenant/politicas"),
    ("PATCH", "/api/admin/tenant/politicas"),
]


def test_rutas_catalogo_existen_en_la_app() -> None:
    rutas_reales: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods: set[str] = set(getattr(route, "methods", set()))
        if path and methods:
            for m in methods:
                if m in {"GET", "POST", "PATCH", "DELETE"}:
                    rutas_reales.add((m, path))

    for metodo, ruta in RUTAS_CATALOGO_ESPERADAS:
        assert (
            metodo,
            ruta,
        ) in rutas_reales, f"Falta ruta {metodo} {ruta} en app.routes"


def test_readme_documenta_catalogo_y_politicas() -> None:
    assert "## Catálogo y configuración (C-04)" in README

    for metodo, ruta in RUTAS_CATALOGO_ESPERADAS:
        esperado = f"`{metodo} {ruta}`"
        assert esperado in README or f"{metodo} {ruta}" in README, (
            f"Falta documentar {metodo} {ruta} en README.md"
        )

    # Verificamos conceptos clave en README
    assert "baja lógica" in README.lower()
    assert "Recurso.CONFIGURACION" in README or "CONFIGURACION" in README
    assert "Box 1" in README


def test_changes_y_readme_reflejan_estado_c04() -> None:
    assert "[C-04] `catalogo-configuracion`" in CHANGES
    assert "C-04 `catalogo-configuracion`" in README


def test_readme_documenta_las_cinco_prestaciones_base() -> None:
    for prestacion in ("Limpieza", "Consulta", "Arreglo", "Endodoncia", "Extracción"):
        assert prestacion in README, f"Falta prestación base {prestacion} en README.md"
