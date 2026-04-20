from pydantic import BaseModel
from typing import List


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    message: str


class SessionInfoResponse(BaseModel):
    session_id: str
    session_name: str
    user_id: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    user_id: str
    sessions: List[SessionInfoResponse]
