import requests
from fastapi import HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings


def verify_google_token(token: str) -> dict:
    """Verify a Google ID token and return basic profile info."""
    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except ValueError as exc:
        raise ValueError(f"Invalid Google token: {exc}") from exc

    return {
        "email": idinfo["email"],
        "name": idinfo.get("name", ""),
        "picture": idinfo.get("picture", ""),
        "sub": idinfo["sub"],  # Google user ID
    }


def get_user_info_from_access_token(access_token: str) -> dict:
    url = "https://www.googleapis.com/oauth2/v1/userinfo"
    response = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch user info from Google")
    return response.json()
