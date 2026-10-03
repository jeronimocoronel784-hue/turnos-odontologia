"""Logger estándar. NUNCA loguear PHI (DNI, teléfono, datos clínicos) — R9."""

import logging
import sys

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

logger = logging.getLogger("turnos")
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False
