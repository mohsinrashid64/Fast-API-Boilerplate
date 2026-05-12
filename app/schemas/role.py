from pydantic import BaseModel
from typing import Optional, List


# ─── Permission Schemas ───

class PermissionBase(BaseModel):
    name: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionResponse(PermissionBase):
    id: int

    class Config:
        from_attributes = True


# ─── Role Schemas ───

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    permissions: Optional[List[str]] = []  # List of permission names to attach


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None  # If provided, replaces all permissions


class RoleResponse(RoleBase):
    id: int
    permissions: List[PermissionResponse] = []

    class Config:
        from_attributes = True


# ─── User-Role Assignment ───

class AssignRoleRequest(BaseModel):
    user_id: int
    role_name: str


class UserRolesResponse(BaseModel):
    user_id: int
    username: str
    roles: List[RoleResponse] = []

    class Config:
        from_attributes = True
