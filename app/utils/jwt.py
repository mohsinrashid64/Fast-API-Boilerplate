from datetime import datetime, timedelta
from typing import List
from jose import JWTError, jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30          # 30 minutes
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

bearer_scheme = HTTPBearer()


def create_access_token(data: dict, roles: List[str] = None, permissions: List[str] = None) -> str:
    """Create a short-lived JWT access token with roles and permissions in claims."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "type": "access",
        "roles": roles or [],
        "permissions": permissions or [],
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a long-lived JWT refresh token (no roles/permissions — just identity)."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "type": "refresh",
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> dict:
    """Decode and verify an access token. Rejects refresh tokens."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type — expected access token")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def verify_refresh_token(token: str) -> dict:
    """Decode and verify a refresh token. Rejects access tokens."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type — expected refresh token")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """
    Extract and validate the user from the access token.
    Returns dict with id, roles, and permissions.
    """
    token = credentials.credentials
    try:
        payload = verify_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return {
            "id": user_id,
            "roles": payload.get("roles", []),
            "permissions": payload.get("permissions", []),
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
