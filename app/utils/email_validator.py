import re

import dns.exception
import dns.resolver

# Only emails from these providers are accepted at signup. Edit to suit your app.
KNOWN_EMAIL_PROVIDERS = {"gmail.com", "outlook.com", "yahoo.com", "icloud.com", "hotmail.com"}

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email_format(email: str) -> bool:
    """Validate the format of an email address using regex."""
    return _EMAIL_REGEX.match(email) is not None


def validate_email_domain(email: str) -> str:
    """Ensure the email belongs to a known provider. Raises ValueError otherwise."""
    domain = email.split("@")[-1].lower()
    if domain not in KNOWN_EMAIL_PROVIDERS:
        raise ValueError(f"The domain '{domain}' is not a known email provider.")
    return domain


def has_mx_records(domain: str) -> bool:
    """Blocking DNS lookup: True if the domain has MX records.

    Call it via `asyncio.to_thread` from async code.
    """
    try:
        return bool(dns.resolver.resolve(domain, "MX", lifetime=5))
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        return False
    except dns.exception.Timeout:
        # Don't block signups because of a flaky resolver.
        return True
