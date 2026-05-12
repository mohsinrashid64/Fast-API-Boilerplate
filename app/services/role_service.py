from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Role, Permission, User


class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Permissions ───

    async def create_permission(self, name: str, description: Optional[str] = None) -> Permission:
        existing = await self.db.execute(select(Permission).where(Permission.name == name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Permission '{name}' already exists")

        perm = Permission(name=name, description=description)
        self.db.add(perm)
        await self.db.commit()
        await self.db.refresh(perm)
        return perm

    async def get_all_permissions(self) -> List[Permission]:
        result = await self.db.execute(select(Permission))
        return result.scalars().all()

    async def delete_permission(self, permission_id: int):
        result = await self.db.execute(select(Permission).where(Permission.id == permission_id))
        perm = result.scalar_one_or_none()
        if not perm:
            raise HTTPException(status_code=404, detail="Permission not found")
        await self.db.delete(perm)
        await self.db.commit()
        return {"detail": "Permission deleted"}

    # ─── Roles ───

    async def create_role(self, name: str, description: Optional[str] = None, permission_names: List[str] = None) -> Role:
        existing = await self.db.execute(select(Role).where(Role.name == name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Role '{name}' already exists")

        role = Role(name=name, description=description)

        if permission_names:
            perms_result = await self.db.execute(
                select(Permission).where(Permission.name.in_(permission_names))
            )
            perms = perms_result.scalars().all()
            found_names = {p.name for p in perms}
            missing = set(permission_names) - found_names
            if missing:
                raise HTTPException(status_code=400, detail=f"Permissions not found: {', '.join(missing)}")
            role.permissions = list(perms)

        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def get_all_roles(self) -> List[Role]:
        result = await self.db.execute(select(Role).options(selectinload(Role.permissions)))
        return result.scalars().all()

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        result = await self.db.execute(
            select(Role).where(Role.name == name).options(selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def update_role(self, role_id: int, name: Optional[str] = None, description: Optional[str] = None, permission_names: Optional[List[str]] = None) -> Role:
        result = await self.db.execute(
            select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        )
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        if name:
            role.name = name
        if description is not None:
            role.description = description

        if permission_names is not None:
            perms_result = await self.db.execute(
                select(Permission).where(Permission.name.in_(permission_names))
            )
            perms = perms_result.scalars().all()
            found_names = {p.name for p in perms}
            missing = set(permission_names) - found_names
            if missing:
                raise HTTPException(status_code=400, detail=f"Permissions not found: {', '.join(missing)}")
            role.permissions = list(perms)

        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def delete_role(self, role_id: int):
        result = await self.db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        await self.db.delete(role)
        await self.db.commit()
        return {"detail": "Role deleted"}

    # ─── User-Role Assignment ───

    async def assign_role_to_user(self, user_id: int, role_name: str):
        user_result = await self.db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        role = await self.get_role_by_name(role_name)
        if not role:
            raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found")

        if role in user.roles:
            raise HTTPException(status_code=400, detail=f"User already has role '{role_name}'")

        user.roles.append(role)
        await self.db.commit()

        return {
            "user_id": user.id,
            "username": user.username,
            "roles": [{"id": r.id, "name": r.name, "description": r.description, "permissions": [{"id": p.id, "name": p.name, "description": p.description} for p in r.permissions]} for r in user.roles],
        }

    async def remove_role_from_user(self, user_id: int, role_name: str):
        user_result = await self.db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        role = await self.get_role_by_name(role_name)
        if not role:
            raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found")

        if role not in user.roles:
            raise HTTPException(status_code=400, detail=f"User does not have role '{role_name}'")

        user.roles.remove(role)
        await self.db.commit()

        return {
            "user_id": user.id,
            "username": user.username,
            "roles": [{"id": r.id, "name": r.name, "description": r.description, "permissions": [{"id": p.id, "name": p.name, "description": p.description} for p in r.permissions]} for r in user.roles],
        }

    async def get_user_roles(self, user_id: int):
        user_result = await self.db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user_id": user.id,
            "username": user.username,
            "roles": [{"id": r.id, "name": r.name, "description": r.description, "permissions": [{"id": p.id, "name": p.name, "description": p.description} for p in r.permissions]} for r in user.roles],
        }
