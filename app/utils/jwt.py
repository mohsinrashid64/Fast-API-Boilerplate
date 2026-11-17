import jwt
from fastapi import HTTPException, status

from app.core.config import settings
from app.utils.time import utc_in


def create_access_token(data: dict) -> str:
    """Create a signed JWT access token with an expiry."""
    to_encode = data.copy()
    to_encode["exp"] = utc_in(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_access_token(token: str) -> dict:
    """Decode and verify a JWT. Raises 401 on any failure."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
