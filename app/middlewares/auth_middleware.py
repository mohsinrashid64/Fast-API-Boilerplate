from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.utils.jwt import verify_access_token

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Public routes that skip auth
        public_routes = [
            '/', "/auth/login", "/auth/signup", "/auth/google",
            "/auth/google/callback", "/docs", "/openapi.json",
            '/auth/forgot-password', '/auth/reset-password',
            '/otp/verify', '/otp/generate',"/users"
        ]

        if request.url.path in public_routes or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        # Auth handling only — keep this block focused
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Missing or invalid Authorization header"},
            )

        token = auth_header.split(" ")[1]

        try:
            user = verify_access_token(token)
            request.state.user = user  # Attach user info
        except HTTPException as http_exc:
            # Token errors only
            return JSONResponse(
                status_code=http_exc.status_code,
                content={"detail": http_exc.detail},
            )
        except Exception as e:
            # Unexpected token verification issues
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # ✅ Let the rest of the app handle downstream errors
        return await call_next(request)
