"""add sorting_type field

Revision ID: b723eb44048d
Revises: f7c48c06424b
Create Date: 2025-08-13 14:59:07.040571

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b723eb44048d"
down_revision: Union[str, Sequence[str], None] = "f7c48c06424b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "ozon_search_match",
        sa.Column("sorting_type", sa.String(length=50), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("ozon_search_match", "sorting_type")
