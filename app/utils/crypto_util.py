from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# The key MUST come from settings: a key generated at import time would change on
# every restart (and differ per worker), making previously issued values undecryptable.


@lru_cache(maxsize=2)
def _fernet(key: str) -> Fernet:
    return Fernet(key.encode())


def _cipher() -> Fernet:
    if not settings.ENCRYPTION_KEY:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    return _fernet(settings.ENCRYPTION_KEY)


def encrypt_data(data: int | str) -> str:
    return _cipher().encrypt(str(data).encode()).decode()


def decrypt_data(encrypted_data: str) -> int:
    """Decrypt a value produced by `encrypt_data`. Raises ValueError if invalid."""
    try:
        return int(_cipher().decrypt(encrypted_data.encode()).decode())
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Invalid encrypted value") from exc
