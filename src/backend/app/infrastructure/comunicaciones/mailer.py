"""Cliente transaccional de correo electrónico SMTP / Mailhog (C-08, RN-CO-03, R9).

Nunca loguea direcciones de correo ni contenido clínico (R9).
"""

import asyncio
import smtplib
import uuid
from email.message import EmailMessage
from urllib.parse import urlparse

from app.shared.logging import logger
from app.shared.settings import get_settings


def _enviar_smtp_sync(smtp_url: str, destino: str, asunto: str, cuerpo: str) -> str:
    parsed = urlparse(smtp_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1025
    msg_id = f"<mail.{uuid.uuid4().hex[:16]}@turnos.local>"

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = "no-reply@consultorio.local"
    msg["To"] = destino
    msg["Message-ID"] = msg_id
    msg.set_content(cuerpo)

    with smtplib.SMTP(host, port, timeout=10) as server:
        if parsed.username and parsed.password:
            server.login(parsed.username, parsed.password)
        server.send_message(msg)
    return msg_id


async def enviar_email_smtp(destino: str, asunto: str, cuerpo: str) -> str:
    """Envía un email transaccional sin bloquear el event loop (R3) ni loguear PHI (R9)."""
    settings = get_settings()
    if not settings.smtp_url:
        msg_id = f"smtp.local.{uuid.uuid4().hex[:16]}"
        logger.info("SMTP en modo local simulado: provider_id=%s", msg_id)
        return msg_id

    return await asyncio.to_thread(_enviar_smtp_sync, settings.smtp_url, destino, asunto, cuerpo)
