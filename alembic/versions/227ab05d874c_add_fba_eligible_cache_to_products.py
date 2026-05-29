"""add_fba_eligible_cache_to_products

Revision ID: 227ab05d874c
Revises: b583e0af2357
Create Date: 2026-05-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '227ab05d874c'
down_revision: Union[str, Sequence[str], None] = 'b583e0af2357'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add FBA eligibility cache columns to products table."""
    op.add_column('products', sa.Column('fba_eligible', sa.Boolean(), nullable=True))
    op.add_column('products', sa.Column('fba_eligible_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove FBA eligibility cache columns from products table."""
    op.drop_column('products', 'fba_eligible_updated_at')
    op.drop_column('products', 'fba_eligible')
