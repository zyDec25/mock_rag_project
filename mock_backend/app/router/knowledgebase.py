from pathlib import Path
from typing import List
from urllib.parse import unquote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from models.knowledgebase import KnowledgeBase
from models.user import User
from schemas.KnowledgeBase import (
    KnowledgeBaseDeleteResponse,
    KnowledgeBaseFileResponse,
    KnowledgeBaseUploadResponse,
)
from service.document_processor import process_document_sync
from service.document_state_machine import DocumentStateMachine, DocumentStatus
from utils.auth import get_current_user
from utils.database import get_db


router = APIRouter(tags=["knowledgebase"])

SUPPORTED_KNOWLEDGEBASE_TYPES = {"pdf", "doc", "docx", "txt"}
STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage" / "file"


def _format_file(file_record: KnowledgeBase) -> KnowledgeBaseFileResponse:
    return KnowledgeBaseFileResponse(
        user_id=file_record.user_id,
        file_name=file_record.file_name,
        status=file_record.status,
        created_at=file_record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        updated_at=file_record.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _get_file_type(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _safe_storage_path(directory: Path, filename: str) -> Path:
    path = (directory / filename).resolve()
    if directory.resolve() not in path.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法文件名: {filename}",
        )
    return path


@router.get("/get_files", response_model=List[KnowledgeBaseFileResponse])
def get_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeBaseFileResponse]:
    user_id = str(current_user.id)
    files = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == user_id)
        .order_by(KnowledgeBase.created_at.desc())
        .all()
    )
    return [_format_file(file_record) for file_record in files]


@router.post("/upload_files", response_model=KnowledgeBaseUploadResponse)
async def upload_files(
    session_id: str | None = Query(None),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeBaseUploadResponse:
    user_id = str(current_user.id)
    storage_owner = user_id

    # 初始化状态机
    state_machine = DocumentStateMachine(db)

    filenames = [file.filename or "" for file in files]
    empty_filenames = [index for index, filename in enumerate(filenames) if not filename]
    if empty_filenames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上传文件名不能为空",
        )

    existing_files = {
        row.file_name
        for row in db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.file_name.in_(filenames),
        )
        .all()
    }
    if existing_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"以下文件已存在，请勿重复上传: {', '.join(sorted(existing_files))}",
        )

    session_dir = STORAGE_ROOT / storage_owner
    session_dir.mkdir(parents=True, exist_ok=True)

    successful_files: list[str] = []
    failed_files: list[str] = []

    for file in files:
        file_name = file.filename or ""
        file_type = _get_file_type(file_name)

        if file_type not in SUPPORTED_KNOWLEDGEBASE_TYPES:
            failed_files.append(f"{file_name}: 仅支持 pdf、doc、docx、txt 文件")
            continue

        try:
            file_content = await file.read()
            if not file_content:
                failed_files.append(f"{file_name}: 文件内容为空")
                continue

            file_path = _safe_storage_path(session_dir, file_name)
            file_path.write_bytes(file_content)

            # 创建文档记录，初始状态为 uploaded
            document = KnowledgeBase(
                user_id=user_id,
                file_name=file_name,
                status=DocumentStatus.UPLOADED.value,
            )
            db.add(document)
            db.flush()  # 获取 document.id

            # TODO: 这里应该触发异步处理管道
            # 暂时直接标记为 parsing 状态，实际应该由后台任务处理
            # from service.document_processor import process_document_async
            # process_document_async.delay(document.id)

            successful_files.append(file_name)

        except Exception as e:
            failed_files.append(f"{file_name}: {str(e)}")
            continue

    if successful_files:
        db.commit()
    else:
        db.rollback()

    if successful_files and not failed_files:
        return KnowledgeBaseUploadResponse(
            status="success",
            message="所有文件上传成功，正在处理中",
            successful_files=successful_files,
            failed_files=[],
            total_files=len(files),
        )

    if successful_files:
        return KnowledgeBaseUploadResponse(
            status="partial_success",
            message=(
                f"部分文件上传成功，{len(successful_files)} 个成功，"
                f"{len(failed_files)} 个失败"
            ),
            successful_files=successful_files,
            failed_files=failed_files,
            total_files=len(files),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "status": "failed",
            "message": "所有文件上传失败",
            "failed_files": failed_files,
            "total_files": len(files),
        },
    )


@router.delete("/delete_file/{file_name}", response_model=KnowledgeBaseDeleteResponse)
def delete_file(
    file_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeBaseDeleteResponse:
    user_id = str(current_user.id)
    decoded_file_name = unquote(file_name)

    file_record = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.file_name == decoded_file_name,
        )
        .first()
    )
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    db.delete(file_record)
    db.commit()

    for storage_dir in (STORAGE_ROOT / user_id,):
        file_path = storage_dir / decoded_file_name
        if file_path.exists() and file_path.is_file():
            file_path.unlink()

    return KnowledgeBaseDeleteResponse(message="Successfully deleted document")


@router.post("/process_file/{file_name}")
def process_file(
    file_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动触发文档处理"""
    user_id = str(current_user.id)
    decoded_file_name = unquote(file_name)

    file_record = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.file_name == decoded_file_name,
        )
        .first()
    )
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # 检查状态
    if file_record.status == DocumentStatus.COMPLETED.value:
        return {
            "message": "文档已处理完成",
            "status": file_record.status,
        }

    if file_record.status not in (
        DocumentStatus.UPLOADED.value,
        DocumentStatus.FAILED.value,
    ):
        return {
            "message": "文档正在处理中",
            "status": file_record.status,
        }

    # 触发处理
    success = process_document_sync(db, file_record.id, STORAGE_ROOT)

    if success:
        return {
            "message": "文档处理成功",
            "status": DocumentStatus.COMPLETED.value,
        }
    else:
        db.refresh(file_record)
        return {
            "message": f"文档处理失败: {file_record.error_message}",
            "status": file_record.status,
            "retry_count": file_record.retry_count,
        }


@router.get("/file_status/{file_name}")
def get_file_status(
    file_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询文档处理状态"""
    from datetime import datetime

    user_id = str(current_user.id)
    decoded_file_name = unquote(file_name)

    file_record = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.file_name == decoded_file_name,
        )
        .first()
    )
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    started_at_str = None
    if file_record.started_at and isinstance(file_record.started_at, datetime):
        started_at_str = file_record.started_at.strftime("%Y-%m-%d %H:%M:%S")

    completed_at_str = None
    if file_record.completed_at and isinstance(file_record.completed_at, datetime):
        completed_at_str = file_record.completed_at.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "file_name": file_record.file_name,
        "status": file_record.status,
        "retry_count": file_record.retry_count,
        "error_message": file_record.error_message,
        "chunk_count": file_record.chunk_count,
        "indexed_count": file_record.indexed_count,
        "started_at": started_at_str,
        "completed_at": completed_at_str,
    }


@router.get("/status_summary")
def get_status_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户所有文档的状态统计"""
    user_id = str(current_user.id)
    state_machine = DocumentStateMachine(db)
    summary = state_machine.get_status_summary(user_id)

    return {
        "user_id": user_id,
        "summary": summary,
        "total": sum(summary.values()),
    }
