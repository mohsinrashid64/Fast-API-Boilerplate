import secrets
from datetime import datetime

from app.utils.time import utc_in


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def otp_expiry(minutes: int = 5) -> datetime:
    """Return the (naive UTC) expiry time for an OTP."""
    return utc_in(minutes=minutes)
