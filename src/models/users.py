import uuid

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, BIGINT, INT, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime
from src.database import Base


class SearchMatchOrm(Base):
    __tablename__ = "telegram_users"

    unique_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text)
    user_fullname: Mapped[str] = mapped_column(String(length=50))
    create_time: Mapped[datetime] = mapped_column(DateTime)
    update_time: Mapped[datetime] = mapped_column(DateTime)


class UrlProductsOrm(Base):
    __tablename__ = "ozon_feedback_stars"

    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ozon_search_match.unique_id"),
        primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_users.unique_id"),
        primary_key=True
    )
    create_time: Mapped[datetime] = mapped_column(DateTime)
    stars: Mapped[int] = mapped_column(INT)
