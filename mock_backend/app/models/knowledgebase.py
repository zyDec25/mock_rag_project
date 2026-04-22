from sqlalchemy import DateTime, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledgebases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="uploaded", index=True
    )
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
