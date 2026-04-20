from pydantic import BaseModel, Field


class ChatOnDocsRequest(BaseModel):
    message: str = Field(..., min_length=1)


class MessageInfoResponse(BaseModel):
    message_id: str
    session_id: str
    user_question: str
    model_answer: str
    documents: str | None = None
    recommended_questions: str | None = None
    think: str | None = None
    status: str = "completed"
    error_message: str | None = None
    retrieval_time_ms: int | None = None
    generation_time_ms: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str
