import logging
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str, html: bool = False) -> None:
    """Send an email via SMTP (credentials come from settings / .env).

    If SMTP is not configured in a non-production environment, the email is
    logged instead of sent, so local development works without credentials.
    """
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD):
        if settings.is_production:
            raise RuntimeError("SMTP is not configured (SMTP_USER / SMTP_PASSWORD)")
        logger.warning("SMTP not configured; email to %s not sent.\nSubject: %s\n%s", to, subject, body)
        return

    msg = MIMEText(body, "html" if html else "plain")
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        start_tls=True,
    )
