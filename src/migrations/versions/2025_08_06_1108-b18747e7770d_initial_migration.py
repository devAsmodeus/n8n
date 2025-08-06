"""initial migration

Revision ID: b18747e7770d
Revises:
Create Date: 2025-08-06 11:08:54.640397

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b18747e7770d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ozon_search_match",
        sa.Column("unique_id", sa.UUID(), nullable=False),
        sa.Column("product_url", sa.String(length=2048), nullable=False),
        sa.Column("sku_id", sa.BIGINT(), nullable=False),
        sa.Column("concat_name", sa.String(length=2048), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("unique_id"),
    )
    op.create_table(
        "ozon_product_characteristics",
        sa.Column("unique_id", sa.UUID(), nullable=False),
        sa.Column("characteristics_name", sa.String(length=150), nullable=False),
        sa.Column("value", sa.String(length=2048), nullable=False),
        sa.ForeignKeyConstraint(
            ["unique_id"],
            ["ozon_search_match.unique_id"],
        ),
        sa.PrimaryKeyConstraint("unique_id", "characteristics_name"),
    )
    op.create_table(
        "ozon_product_top",
        sa.Column("unique_id", sa.UUID(), nullable=False),
        sa.Column("attribute_name", sa.String(length=150), nullable=False),
        sa.Column("value", sa.String(length=2048), nullable=False),
        sa.ForeignKeyConstraint(
            ["unique_id"],
            ["ozon_search_match.unique_id"],
        ),
        sa.PrimaryKeyConstraint("unique_id", "attribute_name"),
    )
    op.create_table(
        "ozon_url_products",
        sa.Column("unique_id", sa.UUID(), nullable=False),
        sa.Column("sorting_type", sa.String(length=50), nullable=False),
        sa.Column("index", sa.INTEGER(), nullable=False),
        sa.Column("product_url", sa.String(length=2048), nullable=False),
        sa.ForeignKeyConstraint(
            ["unique_id"],
            ["ozon_search_match.unique_id"],
        ),
        sa.PrimaryKeyConstraint("unique_id", "sorting_type", "index"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("ozon_url_products")
    op.drop_table("ozon_product_top")
    op.drop_table("ozon_product_characteristics")
    op.drop_table("ozon_search_match")
