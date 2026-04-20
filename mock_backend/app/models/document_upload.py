from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class DocumentUpload(Base):
    __tablename__ = "document_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_type: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="full"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="uploaded"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    upload_time: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
