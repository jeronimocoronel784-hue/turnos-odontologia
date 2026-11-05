"""Chequeo de salud del contenedor, compartido por la API y el worker.

Docker marca el contenedor como `unhealthy` cuando este módulo sale con código
distinto de cero, y EasyPanel no reemplaza el contenedor anterior hasta que el
nuevo está sano. El chequeo anterior —un `try/except` dentro de `python -c` en
una sola línea— era `SyntaxError`, así que todo contenedor nuevo quedaba
`unhealthy` y nunca se activaba.

- API: sana si `GET /api/health` responde 200 (todo bien) o 503 (alguna
  dependencia caída). Un 503 no debe reiniciar el proceso.
- Worker: no expone HTTP; sano si el proceso principal es `app.workers.main`.
"""

from __future__ import annotations

import glob
import sys
import urllib.request

URL_SALUD = "http://127.0.0.1:8000/api/health"
ESTADOS_SANOS = (200, 503)


def api_responde() -> bool:
    """True si la API contesta un estado sano en menos de 3 segundos."""
    try:
        with urllib.request.urlopen(URL_SALUD, timeout=3) as respuesta:
            return respuesta.status in ESTADOS_SANOS
    except Exception:
        return False


def corre_worker() -> bool:
    """True si algún proceso del contenedor es el worker de colas."""
    for ruta in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(ruta, "rb") as archivo:
                if "workers.main" in archivo.read().decode("latin1", "ignore"):
                    return True
        except OSError:
            continue
    return False


def main() -> int:
    """Código de salida para Docker: 0 sano, 1 enfermo."""
    return 0 if (api_responde() or corre_worker()) else 1


if __name__ == "__main__":
    sys.exit(main())
