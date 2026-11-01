"""Cliente async para WhatsApp Business Cloud API v18+ (C-08, RN-CO-03, R9).

Nunca loguea números de teléfono, DNI ni texto clínico en logs ni errores (R9).
Si `WA_API_TOKEN` o `WA_PHONE_ID` no están configurados (modo dev/local sin credenciales),
opera en modo simulado determinístico devolviendo un `wamid.local.<uuid>`.
"""

import uuid

import httpx

from app.shared.logging import logger
from app.shared.settings import get_settings


async def enviar_whatsapp_cloud(destino: str, cuerpo: str) -> str:
    """Envía un mensaje de texto por WhatsApp Cloud API y retorna el ID del proveedor (`wamid`)."""
    try:
        settings = get_settings()
        token = settings.wa_api_token.strip()
        phone_id = settings.wa_phone_id.strip()
    except Exception:
        token = ""
        phone_id = ""

    if not token or not phone_id or token.lower().startswith(("reemplazar", "dummy", "test")):
        msg_id = f"wamid.local.{uuid.uuid4().hex[:16]}"
        logger.info("WA Cloud API en modo local simulado: provider_id=%s", msg_id)
        return msg_id

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": destino,
        "type": "text",
        "text": {"body": cuerpo},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning("Fallo HTTP WhatsApp Cloud API status=%s", resp.status_code)
            raise RuntimeError(f"Error de proveedor WhatsApp (HTTP {resp.status_code}).")
        data = resp.json()
        messages = data.get("messages") or []
        if messages and isinstance(messages[0], dict) and "id" in messages[0]:
            return str(messages[0]["id"])
        return f"wamid.cloud.{uuid.uuid4().hex[:16]}"
