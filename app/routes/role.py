from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import RoleService
from app.schemas import (
    RoleCreate, RoleUpdate, RoleResponse,
    PermissionCreate, PermissionResponse,
    AssignRoleRequest, UserRolesResponse,
)
from app.utils.rbac import require_role

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])


# ─── Permissions ───

@router.post(
    "/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new permission",
    description="Create a new permission entry (e.g. 'products:read', 'users:manage'). Only accessible by admins.",
)
async def create_permission(
    data: PermissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.create_permission(name=data.name, description=data.description)


@router.get(
    "/permissions",
    response_model=List[PermissionResponse],
    summary="List all permissions",
    description="Retrieve all available permissions in the system. Only accessible by admins.",
)
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.get_all_permissions()


@router.delete(
    "/permissions/{permission_id}",
    summary="Delete a permission",
    description="Permanently delete a permission by its ID. This also removes it from all roles. Only accessible by admins.",
)
async def delete_permission(
    permission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.delete_permission(permission_id)


# ─── Roles ───

@router.post(
    "/",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new role",
    description="Create a new role with optional permissions. Provide a list of permission names to attach. Only accessible by admins.",
)
async def create_role(
    data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.create_role(name=data.name, description=data.description, permission_names=data.permissions)


@router.get(
    "/",
    response_model=List[RoleResponse],
    summary="List all roles",
    description="Retrieve all roles with their associated permissions. Only accessible by admins.",
)
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.get_all_roles()


@router.put(
    "/{role_id}",
    response_model=RoleResponse,
    summary="Update a role",
    description="Update a role's name, description, and/or permissions. If permissions list is provided, it replaces all current permissions. Only accessible by admins.",
)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.update_role(
        role_id=role_id,
        name=data.name,
        description=data.description,
        permission_names=data.permissions,
    )


@router.delete(
    "/{role_id}",
    summary="Delete a role",
    description="Permanently delete a role by its ID. This also removes the role from all users. Only accessible by admins.",
)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.delete_role(role_id)


# ─── User-Role Assignment ───

@router.post(
    "/assign",
    response_model=UserRolesResponse,
    summary="Assign a role to a user",
    description="Assign an existing role to a user by user ID and role name. The user will gain all permissions associated with the role. Only accessible by admins.",
)
async def assign_role(
    data: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.assign_role_to_user(user_id=data.user_id, role_name=data.role_name)


@router.post(
    "/revoke",
    response_model=UserRolesResponse,
    summary="Revoke a role from a user",
    description="Remove an assigned role from a user. The user will lose all permissions associated with the revoked role. Only accessible by admins.",
)
async def revoke_role(
    data: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.remove_role_from_user(user_id=data.user_id, role_name=data.role_name)


@router.get(
    "/user/{user_id}",
    response_model=UserRolesResponse,
    summary="Get a user's roles",
    description="Retrieve all roles and their permissions assigned to a specific user. Only accessible by admins.",
)
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    service = RoleService(db)
    return await service.get_user_roles(user_id)
