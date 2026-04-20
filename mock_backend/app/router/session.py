import json
import time
import uuid
from io import BytesIO
from datetime import datetime, timedelta
from typing import AsyncGenerator, List

import pdfplumber
from docx import Document
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DbSession

from models.document_upload import DocumentUpload
from models.message import Message
from models.session import Session as ChatSession
from models.user import User
from schemas.DocumentUpload import (
    DocumentUploadResponse,
    QuickParseResponse,
    SessionDocumentSummary,
    SessionDocumentsResponse,
)
from schemas.Message import (
    ChatOnDocsRequest,
    MessageInfoResponse,
)
from schemas.Session import (
    CreateSessionResponse,
    SessionInfoResponse,
    SessionListResponse,
)
from utils.auth import get_current_user
from utils.database import SessionLocal, get_db
from utils.redis_client import (
    QUICK_PARSE_TTL_SECONDS,
    get_quick_parse_content,
    get_quick_parse_ttl,
    set_quick_parse_content,
)


router = APIRouter(tags=["session"])

SUPPORTED_QUICK_PARSE_TYPES = {"pdf", "docx", "txt"}
MAX_QUICK_PARSE_TEXT_LENGTH = 4000
MAX_QUICK_PARSE_PDF_PAGES = 4


def _format_session(session: ChatSession) -> SessionInfoResponse:
    return SessionInfoResponse(
        session_id=session.session_id,
        session_name=session.session_name,
        user_id=session.user_id,
        created_at=session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        updated_at=session.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _format_message(
    message: Message, documents: str | None = None
) -> MessageInfoResponse:
    return MessageInfoResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        user_question=message.user_question,
        model_answer=message.model_answer,
        documents=documents if documents is not None else message.documents,
        recommended_questions=message.recommended_questions,
        think=message.think,
        status=message.status,
        error_message=message.error_message,
        retrieval_time_ms=message.retrieval_time_ms,
        generation_time_ms=message.generation_time_ms,
        started_at=(
            message.started_at.strftime("%Y-%m-%d %H:%M:%S")
            if message.started_at
            else None
        ),
        completed_at=(
            message.completed_at.strftime("%Y-%m-%d %H:%M:%S")
            if message.completed_at
            else None
        ),
        created_at=message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        updated_at=message.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _format_document(document: DocumentUpload) -> DocumentUploadResponse:
    return DocumentUploadResponse.model_validate(document)


def _get_owned_session(
    session_id: str, current_user: User, db: DbSession
) -> ChatSession:
    chat_session = (
        db.query(ChatSession)
        .filter(
            ChatSession.session_id == session_id,
            ChatSession.user_id == str(current_user.id),
        )
        .first()
    )
    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    return chat_session


def _build_mock_answer(question: str, quick_parse_content: str | None = None) -> str:
    answer = (
        "这是 mock 后端生成的回答。"
        f"我已收到你的问题：{question}。"
        "后续接入真实 RAG 流程后，这里会替换为检索文档和大模型生成结果。"
    )
    if quick_parse_content:
        answer += (
            "当前会话已读取快速解析文档上下文，"
            f"缓存内容长度为 {len(quick_parse_content)} 字符。"
        )
    return answer


def _build_recommended_questions(question: str) -> list[str]:
    return [
        "能展开说明相关背景吗？",
        "有哪些关键风险需要注意？",
        f"围绕“{question[:20]}”还有哪些后续问题？",
    ]


def _make_session_name(question: str) -> str:
    stripped = question.strip()
    return stripped[:20] if stripped else "新对话"


def _get_document_type(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _decode_txt(file_content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return file_content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_content.decode("utf-8", errors="ignore")


def _parse_docx(file_content: bytes) -> str:
    document = Document(BytesIO(file_content))
    return "\n".join(
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    )


def _parse_pdf(file_content: bytes) -> str:
    with pdfplumber.open(BytesIO(file_content)) as pdf:
        if len(pdf.pages) > MAX_QUICK_PARSE_PDF_PAGES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"PDF 快速解析最多支持 {MAX_QUICK_PARSE_PDF_PAGES} 页",
            )
        page_texts = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(text.strip() for text in page_texts if text.strip())


def _parse_quick_document(document_type: str, file_content: bytes) -> str:
    if document_type == "txt":
        parsed_content = _decode_txt(file_content)
    elif document_type == "docx":
        parsed_content = _parse_docx(file_content)
    elif document_type == "pdf":
        parsed_content = _parse_pdf(file_content)
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 pdf、docx、txt 文件",
        )

    parsed_content = parsed_content.strip()
    if not parsed_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未解析到有效文本内容",
        )

    if (
        document_type in {"txt", "docx"}
        and len(parsed_content) > MAX_QUICK_PARSE_TEXT_LENGTH
    ):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"TXT/DOCX 快速解析最多支持 {MAX_QUICK_PARSE_TEXT_LENGTH} 字符",
        )

    return parsed_content


def _build_quick_parse_reference(session_id: str, content: str) -> dict:
    document_id = f"quick_parse:{session_id}"
    document_name = "快速解析文档"
    return {
        "id": document_id,
        "document_id": document_id,
        "document_name": document_name,
        "content_with_weight": content,
        "positions": [],
        "doc_id": document_id,
        "doc_name": document_name,
        "content": content,
        "similarity": 1.0,
        "source": "quick_parse",
    }


def _hydrate_quick_parse_documents(
    raw_documents: str | None, session_id: str, quick_parse_content: str | None
) -> str | None:
    if not raw_documents or not quick_parse_content:
        return raw_documents

    try:
        documents = json.loads(raw_documents)
    except json.JSONDecodeError:
        return raw_documents

    if not isinstance(documents, list):
        return raw_documents

    changed = False
    document_id = f"quick_parse:{session_id}"
    for document in documents:
        if not isinstance(document, dict):
            continue

        is_quick_parse = (
            document.get("source") == "quick_parse"
            or document.get("doc_id") == document_id
            or document.get("document_id") == document_id
        )
        if not is_quick_parse:
            continue

        current_content = (
            document.get("content") or document.get("content_with_weight") or ""
        )
        if len(current_content) >= len(quick_parse_content):
            continue

        document.update(_build_quick_parse_reference(session_id, quick_parse_content))
        changed = True

    if not changed:
        return raw_documents

    return json.dumps(documents, ensure_ascii=False)


def _sse_event(event: str, payload: dict | str) -> str:
    data = (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    )
    return f"event: {event}\ndata: {data}\n\n"


def _elapsed_ms(start_time: float) -> int:
    return max(0, int((time.perf_counter() - start_time) * 1000))


async def _mock_chat_stream(
    message_id: str,
    session_id: str,
    user_id: str,
    question: str,
) -> AsyncGenerator[str, None]:
    stream_db = SessionLocal()
    retrieval_start = time.perf_counter()
    generation_start = 0.0
    model_answer = ""
    documents: list[dict] = []
    recommended_questions: list[str] = []

    try:
        message = (
            stream_db.query(Message).filter(Message.message_id == message_id).first()
        )
        if message is None:
            raise RuntimeError("消息记录不存在")

        message.status = "retrieving"
        message.started_at = message.started_at or datetime.now()
        stream_db.commit()

        quick_parse_content = await get_quick_parse_content(session_id)
        if quick_parse_content:
            documents.append(
                _build_quick_parse_reference(session_id, quick_parse_content)
            )

        retrieval_time_ms = _elapsed_ms(retrieval_start)
        message.status = "generating"
        message.documents = json.dumps(documents, ensure_ascii=False)
        message.retrieval_time_ms = retrieval_time_ms
        stream_db.commit()

        yield _sse_event("message", {"documents": documents})

        generation_start = time.perf_counter()
        recommended_questions = _build_recommended_questions(question)
        model_answer = _build_mock_answer(question, quick_parse_content)

        for index in range(0, len(model_answer), 18):
            yield _sse_event(
                "message",
                {"content": model_answer[index : index + 18]},
            )

        yield _sse_event(
            "message",
            {"recommended_questions": recommended_questions},
        )

        completed_at = datetime.now()
        message.model_answer = model_answer
        message.recommended_questions = json.dumps(
            recommended_questions, ensure_ascii=False
        )
        message.think = "mock 阶段未接入真实推理过程"
        message.status = "completed"
        message.generation_time_ms = _elapsed_ms(generation_start)
        message.completed_at = completed_at

        chat_session = (
            stream_db.query(ChatSession)
            .filter(
                ChatSession.session_id == session_id,
                ChatSession.user_id == user_id,
            )
            .first()
        )
        if chat_session and chat_session.session_name == "新对话":
            chat_session.session_name = _make_session_name(question)

        stream_db.commit()
        yield _sse_event("end", "[DONE]")
    except Exception as exc:
        stream_db.rollback()

        message = (
            stream_db.query(Message).filter(Message.message_id == message_id).first()
        )
        if message is not None:
            message.status = "failed"
            message.error_message = str(exc)
            message.model_answer = model_answer
            message.documents = json.dumps(documents, ensure_ascii=False)
            message.recommended_questions = json.dumps(
                recommended_questions, ensure_ascii=False
            )
            message.retrieval_time_ms = (
                message.retrieval_time_ms
                if message.retrieval_time_ms is not None
                else _elapsed_ms(retrieval_start)
            )
            if generation_start:
                message.generation_time_ms = _elapsed_ms(generation_start)
            message.completed_at = datetime.now()
            stream_db.commit()

        yield _sse_event("error", {"error": str(exc), "status": "failed"})
        yield _sse_event("end", "[DONE]")
    finally:
        stream_db.close()


@router.post("/create_session", response_model=CreateSessionResponse)
def create_session(
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CreateSessionResponse:
    session_id = uuid.uuid4().hex[:16]
    chat_session = ChatSession(
        session_id=session_id,
        session_name="新对话",
        user_id=str(current_user.id),
    )

    db.add(chat_session)
    db.commit()

    return CreateSessionResponse(
        session_id=session_id,
        status="success",
        message="Session created successfully",
    )


@router.get("/get_sessions", response_model=SessionListResponse)
def get_sessions(
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> SessionListResponse:
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == str(current_user.id))
        .order_by(ChatSession.created_at.desc())
        .all()
    )

    return SessionListResponse(
        user_id=str(current_user.id),
        sessions=[_format_session(session) for session in sessions],
    )


@router.get("/get_messages", response_model=List[MessageInfoResponse])
async def get_messages(
    session_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[MessageInfoResponse]:
    _get_owned_session(session_id, current_user, db)

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    quick_parse_content = await get_quick_parse_content(session_id)
    return [
        _format_message(
            message,
            documents=_hydrate_quick_parse_documents(
                message.documents, session_id, quick_parse_content
            ),
        )
        for message in messages
    ]


@router.post("/chat_on_docs")
async def chat_on_docs(
    session_id: str = Query(...),
    payload: ChatOnDocsRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    question = payload.message.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="问题不能为空",
        )

    _get_owned_session(session_id, current_user, db)

    now = datetime.now()
    message = Message(
        session_id=session_id,
        user_question=question,
        model_answer="",
        documents=json.dumps([], ensure_ascii=False),
        recommended_questions=json.dumps([], ensure_ascii=False),
        think=None,
        status="pending",
        started_at=now,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return StreamingResponse(
        _mock_chat_stream(
            message_id=message.message_id,
            session_id=session_id,
            user_id=str(current_user.id),
            question=question,
        ),
        media_type="text/event-stream",
    )


@router.post("/quick_parse", response_model=QuickParseResponse)
async def quick_parse(
    session_id: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> QuickParseResponse:
    _get_owned_session(session_id, current_user, db)

    filename = file.filename or ""
    document_type = _get_document_type(filename)
    if not filename or document_type not in SUPPORTED_QUICK_PARSE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 pdf、docx、txt 文件",
        )

    file_content = await file.read()
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件内容不能为空",
        )

    now = datetime.now()
    try:
        parsed_content = _parse_quick_document(document_type, file_content)
        await set_quick_parse_content(session_id, parsed_content)
    except HTTPException as exc:
        document = DocumentUpload(
            session_id=session_id,
            document_name=filename,
            document_type=document_type,
            file_size=len(file_content),
            parse_type="quick",
            status="failed",
            error_message=str(exc.detail),
            error_code=exc.status_code,
            started_at=now,
            completed_at=datetime.now(),
        )
        db.add(document)
        db.commit()
        raise exc
    except Exception as exc:
        document = DocumentUpload(
            session_id=session_id,
            document_name=filename,
            document_type=document_type,
            file_size=len(file_content),
            parse_type="quick",
            status="failed",
            error_message=str(exc),
            error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            started_at=now,
            completed_at=datetime.now(),
        )
        db.add(document)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文档快速解析失败: {str(exc)}",
        ) from exc

    completed_at = datetime.now()
    (
        db.query(DocumentUpload)
        .filter(
            DocumentUpload.session_id == session_id,
            DocumentUpload.parse_type == "quick",
            DocumentUpload.status == "cached",
        )
        .update(
            {
                DocumentUpload.status: "expired",
                DocumentUpload.completed_at: completed_at,
            },
            synchronize_session=False,
        )
    )
    document = DocumentUpload(
        session_id=session_id,
        document_name=filename,
        document_type=document_type,
        file_size=len(file_content),
        parse_type="quick",
        status="cached",
        content_length=len(parsed_content),
        started_at=now,
        completed_at=completed_at,
        expires_at=completed_at + timedelta(seconds=QUICK_PARSE_TTL_SECONDS),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return QuickParseResponse(
        status="success",
        message="文档快速解析成功（mock）",
        session_id=session_id,
        document=_format_document(document),
    )


@router.get("/get_parsed_content")
async def get_parsed_content(
    session_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    _get_owned_session(session_id, current_user, db)
    content = await get_quick_parse_content(session_id)
    ttl = await get_quick_parse_ttl(session_id)
    return {
        "session_id": session_id,
        "has_content": content is not None,
        "content": content,
        "ttl_seconds": ttl if ttl > 0 else 0,
    }


@router.get(
    "/sessions/{session_id}/documents",
    response_model=SessionDocumentsResponse,
)
def get_session_documents(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> SessionDocumentsResponse:
    _get_owned_session(session_id, current_user, db)

    documents = (
        db.query(DocumentUpload)
        .filter(DocumentUpload.session_id == session_id)
        .order_by(DocumentUpload.upload_time.desc())
        .all()
    )

    return SessionDocumentsResponse(
        session_id=session_id,
        has_documents=bool(documents),
        documents=[_format_document(document) for document in documents],
        total_count=len(documents),
    )


@router.get(
    "/sessions/{session_id}/documents/summary",
    response_model=SessionDocumentSummary,
)
def get_session_document_summary(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> SessionDocumentSummary:
    _get_owned_session(session_id, current_user, db)

    documents = (
        db.query(DocumentUpload)
        .filter(DocumentUpload.session_id == session_id)
        .order_by(DocumentUpload.upload_time.desc())
        .all()
    )
    latest_document = documents[0] if documents else None

    return SessionDocumentSummary(
        session_id=session_id,
        has_documents=latest_document is not None,
        latest_document_name=latest_document.document_name if latest_document else None,
        latest_document_type=latest_document.document_type if latest_document else None,
        latest_upload_time=latest_document.upload_time if latest_document else None,
        total_documents=len(documents),
    )
