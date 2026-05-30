"""add_analysis_bucket_restriction_kind

Revision ID: a1b2c3d4e5f6
Revises: 3f8a1c29d4e7
Create Date: 2026-05-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3f8a1c29d4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add analysis_bucket and restriction_kind to job_items."""
    op.add_column('job_items', sa.Column('analysis_bucket', sa.String(25), nullable=True))
    op.add_column('job_items', sa.Column('restriction_kind', sa.String(25), nullable=True))
    op.create_index('ix_job_items_analysis_bucket', 'job_items', ['analysis_bucket'])


def downgrade() -> None:
    """Remove analysis_bucket and restriction_kind from job_items."""
    op.drop_index('ix_job_items_analysis_bucket', table_name='job_items')
    op.drop_column('job_items', 'restriction_kind')
    op.drop_column('job_items', 'analysis_bucket')
