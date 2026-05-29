"""add_fba_eligible_marketplace_scope

Revision ID: 3f8a1c29d4e7
Revises: 227ab05d874c
Create Date: 2026-05-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8a1c29d4e7'
down_revision: Union[str, Sequence[str], None] = '227ab05d874c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add marketplace scope to FBA eligibility cache."""
    op.add_column('products', sa.Column('fba_eligible_marketplace', sa.String(5), nullable=True))


def downgrade() -> None:
    """Remove marketplace scope from FBA eligibility cache."""
    op.drop_column('products', 'fba_eligible_marketplace')
