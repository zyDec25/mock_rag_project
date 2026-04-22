from datetime import datetime

from pydantic import BaseModel


class KnowledgeBaseFileResponse(BaseModel):
    user_id: str
    file_name: str
    status: str = "uploaded"
    created_at: str
    updated_at: str


class KnowledgeBaseResponse(BaseModel):
    id: int
    user_id: str
    file_name: str
    status: str = "completed"
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    user_id: str
    files: list[KnowledgeBaseResponse]


class KnowledgeBaseUploadResponse(BaseModel):
    status: str
    message: str
    successful_files: list[str]
    failed_files: list[str] = []
    total_files: int


class KnowledgeBaseDeleteResponse(BaseModel):
    message: str
