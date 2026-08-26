"""
Real, provider-agnostic SMTP email client — F21 Safety/SOS trusted-contact
notification (IMPLEMENTATION_BLUEPRINT.md F21). No specific commercial SMS
vendor was ever decided anywhere in the seven engineering documents (see
PHASE_STATUS.md's Phase 8 section) — SMS is explicitly NOT implemented
here rather than fabricated against an unspecified provider. Email uses
Python's own stdlib `smtplib`/`email` — no vendor SDK, works with any SMTP
relay via `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/
`SMTP_FROM_EMAIL`. Mirrors `expo_push_client.py`'s pattern: one typed
failure mode (`EmailDeliveryError`), never a raw `smtplib` exception
escaping to a caller.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("app.email")


class EmailDeliveryError(Exception):
    """Raised only for a transport-level failure (connection/auth/send)."""


def _send_sync(to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    assert settings.smtp_host and settings.smtp_from_email  # caller already checked

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        server.send_message(message)


async def send_email(to_email: str, subject: str, body: str) -> None:
    """No-op when SMTP is not configured (real, honest degrade — see
    module docstring); raises `EmailDeliveryError` on a genuine transport
    failure so the caller can decide whether to treat it as fatal (F21
    never does — SOS/push delivery is not gated on email succeeding)."""
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        logger.info("smtp_not_configured", extra={"to": "***"})
        return

    try:
        await asyncio.to_thread(_send_sync, to_email, subject, body)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailDeliveryError("Email delivery failed.") from exc
