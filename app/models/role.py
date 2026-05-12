from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, func
from sqlalchemy.orm import relationship
from app.database.db_config import Base


# Association table: Role <-> Permission (many-to-many)
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# Association table: User <-> Role (many-to-many)
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)  # e.g. "admin", "editor", "viewer"
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles", lazy="selectin")
    users = relationship("User", secondary=user_roles, back_populates="roles", lazy="selectin")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)  # e.g. "products:read", "products:write", "users:manage"
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions", lazy="selectin")
