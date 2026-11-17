"""Zona horaria del consultorio (ART) con fallback para entornos sin `tzdata`.

El piloto está en Argentina: las fechas sin offset que llegan del cliente se
interpretan en `America/Argentina/Buenos_Aires` (D2/D12/D13). En Windows sin el
paquete `tzdata` esa zona no existe, así que se usa el offset fijo histórico
(UTC-3, sin horario de verano en Argentina desde 2009).
"""

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ART = "America/Argentina/Buenos_Aires"

try:  # pragma: no cover - depende del entorno, no del código
    ZONA_ART = ZoneInfo(ART)
except ZoneInfoNotFoundError:  # pragma: no cover - Windows sin tzdata
    ZONA_ART = timezone(timedelta(hours=-3), ART)
