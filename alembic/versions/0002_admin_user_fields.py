"""add is_active / is_superuser to users (admin panel)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17 13:05:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET is_verified = false WHERE is_verified IS NULL")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))
        batch_op.add_column(sa.Column("is_superuser", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.alter_column("is_verified", existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("is_verified", existing_type=sa.Boolean(), nullable=True)
        batch_op.drop_column("is_superuser")
        batch_op.drop_column("is_active")
