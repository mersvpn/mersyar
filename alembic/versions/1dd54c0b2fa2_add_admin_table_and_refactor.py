"""add_admin_table_and_refactor

Revision ID: 1dd54c0b2fa2
Revises: ff13492121a5
Create Date: 2025-11-22 04:00:38.062850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '1dd54c0b2fa2'
down_revision: Union[str, None] = 'ff13492121a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- فقط ساخت جدول ادمین‌ها (بقیه موارد حذف شد) ---
    op.create_table('admins',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=True),
    sa.Column('promoted_by', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    # ------------------------------------------------


def downgrade() -> None:
    # --- حذف جدول ادمین‌ها در صورت بازگشت ---
    op.drop_table('admins')
    # --------------------------------------