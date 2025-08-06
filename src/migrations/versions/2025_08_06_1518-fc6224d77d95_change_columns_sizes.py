"""change columns sizes

Revision ID: fc6224d77d95
Revises: b18747e7770d
Create Date: 2025-08-06 15:18:00.238742

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fc6224d77d95"
down_revision: Union[str, Sequence[str], None] = "b18747e7770d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "ozon_product_characteristics",
        "characteristics_name",
        existing_type=sa.VARCHAR(length=150),
        type_=sa.String(length=250),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_product_characteristics",
        "value",
        existing_type=sa.VARCHAR(length=2048),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_product_top",
        "value",
        existing_type=sa.VARCHAR(length=2048),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_search_match",
        "product_url",
        existing_type=sa.VARCHAR(length=2048),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_search_match",
        "concat_name",
        existing_type=sa.VARCHAR(length=2048),
        type_=sa.String(length=2000),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_url_products",
        "product_url",
        existing_type=sa.VARCHAR(length=2048),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "ozon_url_products",
        "product_url",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=2048),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_search_match",
        "concat_name",
        existing_type=sa.String(length=2000),
        type_=sa.VARCHAR(length=2048),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_search_match",
        "product_url",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=2048),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_product_top",
        "value",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=2048),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_product_characteristics",
        "value",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=2048),
        existing_nullable=False,
    )
    op.alter_column(
        "ozon_product_characteristics",
        "characteristics_name",
        existing_type=sa.String(length=250),
        type_=sa.VARCHAR(length=150),
        existing_nullable=False,
    )
