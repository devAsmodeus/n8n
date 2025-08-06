from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, BIGINT, INT, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime
import uuid
from src.database import Base


class SearchMatchOrm(Base):
    __tablename__ = "ozon_search_match"

    unique_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    product_url: Mapped[str] = mapped_column(Text)
    sku_id: Mapped[int] = mapped_column(BIGINT)
    concat_name: Mapped[str] = mapped_column(String(length=2000))
    create_time: Mapped[datetime] = mapped_column(DateTime)
    update_time: Mapped[datetime] = mapped_column(DateTime)


class UrlProductsOrm(Base):
    __tablename__ = "ozon_url_products"

    unique_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_search_match.unique_id", ondelete="CASCADE"),
        primary_key=True
    )
    sorting_type: Mapped[str] = mapped_column(
        String(length=50),
        primary_key=True
    )
    index: Mapped[int] = mapped_column(
        INT,
        primary_key=True
    )
    product_url: Mapped[str] = mapped_column(Text)


class ProductTopOrm(Base):
    __tablename__ = "ozon_product_top"

    unique_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_search_match.unique_id", ondelete="CASCADE"),
        primary_key=True
    )
    attribute_name: Mapped[str] = mapped_column(
        String(length=150),
        primary_key=True
    )
    value: Mapped[str] = mapped_column(Text)


class ProductCharacteristicsOrm(Base):
    __tablename__ = "ozon_product_characteristics"

    unique_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_search_match.unique_id", ondelete="CASCADE"),
        primary_key=True
    )
    characteristics_name: Mapped[str] = mapped_column(
        String(length=250),
        primary_key=True
    )
    value: Mapped[str] = mapped_column(Text)
