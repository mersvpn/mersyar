"""Rename marzban_credentials to panel_credentials and add columns

Revision ID: 20251026_rename_credentials
Revises: 20251025_user_info
Create Date: 2025-11-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251026_rename_credentials'
down_revision: Union[str, None] = '20251025_user_info'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename the table
    op.rename_table('marzban_credentials', 'panel_credentials')
    
    # Add new columns that might be missing
    op.add_column('panel_credentials', sa.Column('panel_type', sa.String(length=50), nullable=False, server_default='marzban'))
    op.add_column('panel_credentials', sa.Column('is_test_panel', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    # Drop the new columns first
    op.drop_column('panel_credentials', 'is_test_panel')
    op.drop_column('panel_credentials', 'panel_type')
    
    # Rename the table back to the old name
    op.rename_table('panel_credentials', 'marzban_credentials')