"""Cliente HTTP de Mercado Pago y verificación criptográfica de firmas (C-12, RN-SE-04, US-031).

Cumple:
- RN-SE-04: secretos y credenciales de MP nunca hardcodeados en código.
- Verificación de cabecera `x-signature` (HMAC-SHA256) con protección contra replay attacks.
- Generación de preferencias con `external_reference` atada a la seña y fecha de expiración sincronizada.
"""

import hashlib
import hmac
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.api.schemas_mercadopago import PreferenciaRead


def calcular_firma_mp(
    data_id: str | None,
    request_id: str | None,
    ts: int,
    secret: str,
) -> str:
    """Calcula el hash HMAC SHA-256 según el formato de manifiesto de Mercado Pago."""
    # Template estándar de Mercado Pago: id:[data.id];request-id:[x-request-id];ts:[ts];
    manifest = f"id:{data_id or ''};request-id:{request_id or ''};ts:{ts};"
    return hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verificar_firma_webhook_mp(
    x_signature: str,
    request_id: str | None,
    data_id: str | None,
    secret: str,
    tolerancia_s: int = 600,
) -> bool:
    """Verifica autenticidad criptográfica e integridad de la notificación de webhook.

    Retorna False si el formato es inválido, si el secreto no coincide o si el timestamp
    está fuera de la ventana de tolerancia (replay attack).
    """
    if not x_signature or not secret:
        return False

    partes = {}
    for item in x_signature.split(","):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            partes[k] = v

    if "ts" not in partes or "v1" not in partes:
        return False

    try:
        ts = int(partes["ts"])
    except ValueError:
        return False

    # Control de expiración (tolerancia por defecto: 10 minutos)
    ahora = int(time.time())
    if abs(ahora - ts) > tolerancia_s:
        return False

    firma_esperada = calcular_firma_mp(
        data_id=data_id,
        request_id=request_id,
        ts=ts,
        secret=secret,
    )

    return hmac.compare_digest(firma_esperada, partes["v1"])


class MercadoPagoClient:
    """Cliente desacoplado para operar contra la API REST de Mercado Pago."""

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.mercadopago.com",
        http_client: httpx.AsyncClient | None = None,
        sandbox: bool = True,
    ) -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.sandbox = sandbox

    async def crear_preferencia(
        self,
        sena_id: uuid.UUID,
        monto: Decimal,
        titulo: str,
        vence_at: datetime,
        paciente_email: str | None = None,
    ) -> PreferenciaRead:
        """Crea una preferencia de pago con external_reference igual a sena_id y vencimiento estricto."""
        pref_id = f"pref_{uuid.uuid4().hex[:12]}"
        init_point = f"https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id={pref_id}"
        sandbox_init_point = (
            f"https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id={pref_id}"
        )

        body: dict[str, Any] = {
            "items": [
                {
                    "title": titulo,
                    "quantity": 1,
                    "currency_id": "ARS",
                    "unit_price": float(monto),
                }
            ],
            "external_reference": str(sena_id),
            "expiration_date_to": vence_at.isoformat(),
        }
        if paciente_email:
            body["payer"] = {"email": paciente_email}

        # Si hay cliente inyectado con transporte real/mock, realiza la llamada HTTP
        if self.http_client:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            resp = await self.http_client.post(
                f"{self.base_url}/checkout/preferences",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return PreferenciaRead(
                id=str(data.get("id", pref_id)),
                init_point=str(data.get("init_point", init_point)),
                sandbox_init_point=str(data.get("sandbox_init_point", sandbox_init_point)),
                external_reference=str(sena_id),
                monto=monto,
                expiration_date_to=vence_at,
            )

        # Modo directo simulado (test / sandbox offline sin llamadas a red externa, R11)
        return PreferenciaRead(
            id=pref_id,
            init_point=init_point,
            sandbox_init_point=sandbox_init_point,
            external_reference=str(sena_id),
            monto=monto,
            expiration_date_to=vence_at,
        )

    async def obtener_pago(self, payment_id: str) -> dict[str, Any]:
        """Consulta los datos de un pago en Mercado Pago."""
        if self.http_client:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            resp = await self.http_client.get(
                f"{self.base_url}/v1/payments/{payment_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

        # Simulado por defecto
        return {
            "id": payment_id,
            "status": "approved",
            "transaction_amount": 10000.0,
            "status_detail": "accredited",
        }
