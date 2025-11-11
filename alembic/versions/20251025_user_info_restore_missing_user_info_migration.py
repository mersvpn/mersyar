"""Restore missing user_info migration

Revision ID: 20251025_user_info
Revises: 97a3534d046a
Create Date: 2025-11-11 20:20:30.670113

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251025_user_info'
down_revision: Union[str, None] = '97a3534d046a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
