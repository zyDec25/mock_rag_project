from datetime import datetime
from typing import List

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: int
    session_id: str
    document_name: str
    document_type: str
    file_size: int | None = None
    parse_type: str = "full"
    status: str = "uploaded"
    retry_count: int = 0
    error_message: str | None = None
    error_code: int | None = None
    chunk_count: int | None = None
    indexed_count: int | None = None
    content_length: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    upload_time: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuickParseResponse(BaseModel):
    status: str
    message: str
    session_id: str
    document: DocumentUploadResponse


class SessionDocumentsResponse(BaseModel):
    session_id: str
    has_documents: bool
    documents: List[DocumentUploadResponse]
    total_count: int


class SessionDocumentSummary(BaseModel):
    session_id: str
    has_documents: bool
    latest_document_name: str | None = None
    latest_document_type: str | None = None
    latest_upload_time: datetime | None = None
    total_documents: int = 0
