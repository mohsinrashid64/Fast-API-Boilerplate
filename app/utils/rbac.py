from typing import List
from fastapi import Depends, HTTPException, status
from app.utils.jwt import get_current_user


def require_role(*allowed_roles: str):
    """
    Dependency that checks if the current user has at least one of the allowed roles.

    Usage in a route:
        current_user = Depends(require_role("admin", "editor"))
    """
    def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        user_roles = current_user.get("roles", [])
        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}",
            )
        return current_user
    return _dependency


def require_permission(*required_permissions: str):
    """
    Dependency that checks if the current user has ALL of the required permissions.

    Usage in a route:
        current_user = Depends(require_permission("products:write"))
    """
    def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        user_permissions = current_user.get("permissions", [])
        missing = [p for p in required_permissions if p not in user_permissions]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Missing permission(s): {', '.join(missing)}",
            )
        return current_user
    return _dependency
