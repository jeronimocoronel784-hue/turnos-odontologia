"""La documentación del change C-13 está al día (tarea E.12, N5/N6/N7).

Verifica contra el contenido real de los archivos (no contra texto inventado):
1. La KB documenta los cinco estados de la liquidación, el reclamo único por obra social
   y período, y las columnas/índices que agrega la migración correctiva `013`.
2. La KB documenta la exportación de liquidaciones (RN-OS-03, US-041) y los roles que
   pueden exportar.
3. El README y el CHANGES documentan la migración `013`, el reclamo único y el
   `saldo_debito`.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
README = (RAIZ / "README.md").read_text(encoding="utf-8")
CHANGES = (RAIZ / "CHANGES.md").read_text(encoding="utf-8")
KB_ACTORES = (RAIZ / "knowledge-base" / "03_actores_y_roles.md").read_text(encoding="utf-8")
KB_DATOS = (RAIZ / "knowledge-base" / "04_modelo_de_datos.md").read_text(encoding="utf-8")
KB_REGLAS = (RAIZ / "knowledge-base" / "05_reglas_de_negocio.md").read_text(encoding="utf-8")
KB_FUNCIONALIDADES = (RAIZ / "knowledge-base" / "06_funcionalidades.md").read_text(encoding="utf-8")
KB_FLUJOS = (RAIZ / "knowledge-base" / "07_flujos_principales.md").read_text(encoding="utf-8")


def test_la_kb_documenta_los_cinco_estados_y_el_reclamo_unico() -> None:
    """§04 documenta los cinco estados (incluida `anulada`) y el reclamo único por OS/período."""
    for estado in ("borrador", "presentada", "pagada", "con_debitos", "anulada"):
        assert estado in KB_DATOS, f"Falta el estado '{estado}' en la KB de datos"

    # El reclamo único por obra social y período, con su excepción (la anulación).
    assert "una sola vez" in KB_DATOS
    assert "anulada" in KB_DATOS
    # La columna `reclamado` y el conteo persistido de la migración `013`.
    assert "reclamado (bool, default true)" in KB_DATOS
    assert "turnos_sin_cobertura (int, default 0)" in KB_DATOS
    # Los índices parciales con `lower(obra_social)`.
    assert "uq_liquidacion_os_borrador" in KB_DATOS
    assert "uq_liquidacion_detalle_turno_reclamado" in KB_DATOS
    assert "lower(obra_social)" in KB_DATOS
    # El saldo de débito es derivado, no una columna.
    assert "saldo_debito" in KB_DATOS

    # La matriz de roles: Dueño y Recepción con CRUD + exportar sobre liquidaciones OS.
    fila = next(
        linea for linea in KB_ACTORES.splitlines() if linea.startswith("| Liquidaciones OS")
    )
    assert fila.count("CRUD + exportar") == 2, fila
    assert "| R |" in fila, fila


def test_la_kb_documenta_la_exportacion_de_liquidaciones() -> None:
    """RN-OS-03, US-041 y el flujo 5 documentan la exportación CSV/JSON de liquidaciones."""
    assert "liquidación exportable (CSV/JSON)" in KB_REGLAS
    assert "US-041 — Liquidación exportable con débitos" in KB_FUNCIONALIDADES
    assert "CA-2 Exportación CSV/JSON; sin presentación electrónica en v1." in KB_FUNCIONALIDADES
    assert "genera exportación CSV/JSON de la liquidación + detalle por turno" in KB_FLUJOS
    # Quién puede exportar según la matriz de roles.
    assert "| Exportación CSV/JSON |" in KB_ACTORES
    assert "liquidaciones de obras sociales" in KB_ACTORES


def test_readme_y_changes_documentan_la_migracion_013() -> None:
    """README y CHANGES nombran la migración correctiva `013` y lo que trae."""
    for documento, nombre in ((README, "README.md"), (CHANGES, "CHANGES.md")):
        assert "013_liquidacion_claim_unico" in documento, f"Falta la migración 013 en {nombre}"
        assert "reclamo único por obra social y período" in documento, nombre
        assert "saldo_debito" in documento, nombre
        assert "turnos_sin_cobertura" in documento, nombre

    assert "## Obras Sociales y Liquidación (C-13)" in README
    assert "uq_liquidacion_detalle_turno_reclamado" in README
    assert "lower(obra_social)" in README
    # La `012` sigue siendo la que crea las tablas: la `013` es correctiva.
    assert "012_obras_sociales_liquidacion" in README
    assert "012_obras_sociales_liquidacion" in CHANGES
