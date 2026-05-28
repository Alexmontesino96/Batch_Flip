"""add_physical_fields_to_job_items

Revision ID: da6f2f66ad61
Revises: 3b1c8eb7194f
Create Date: 2026-05-27 23:59:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "da6f2f66ad61"
down_revision: Union[str, Sequence[str], None] = "3b1c8eb7194f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("job_items", sa.Column("item_weight_grams", sa.Integer(), nullable=True))
    op.add_column("job_items", sa.Column("package_weight_grams", sa.Integer(), nullable=True))
    op.add_column("job_items", sa.Column("item_height", sa.Integer(), nullable=True))
    op.add_column("job_items", sa.Column("item_length", sa.Integer(), nullable=True))
    op.add_column("job_items", sa.Column("item_width", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_items", "item_width")
    op.drop_column("job_items", "item_length")
    op.drop_column("job_items", "item_height")
    op.drop_column("job_items", "package_weight_grams")
    op.drop_column("job_items", "item_weight_grams")
