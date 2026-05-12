from pydantic import BaseModel
from typing import List, Optional


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    roles: List[str] = []
    permissions: List[str] = []


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPayload(BaseModel):
    sub: str
    roles: List[str] = []
    permissions: List[str] = []
    type: str = "access"  # "access" or "refresh"
