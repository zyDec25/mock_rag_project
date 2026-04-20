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
from utils.auth import get_current_user
from utils.database import get_db


router = APIRouter(tags=["knowledgebase"])

SUPPORTED_KNOWLEDGEBASE_TYPES = {"pdf", "doc", "docx", "txt"}
STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage" / "file"


def _format_file(file_record: KnowledgeBase) -> KnowledgeBaseFileResponse:
    return KnowledgeBaseFileResponse(
        user_id=file_record.user_id,
        file_name=file_record.file_name,
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

        file_content = await file.read()
        if not file_content:
            failed_files.append(f"{file_name}: 文件内容为空")
            continue

        file_path = _safe_storage_path(session_dir, file_name)
        file_path.write_bytes(file_content)

        db.add(
            KnowledgeBase(
                user_id=user_id,
                file_name=file_name,
                status="completed",
            )
        )
        successful_files.append(file_name)

    if successful_files:
        db.commit()
    else:
        db.rollback()

    if successful_files and not failed_files:
        return KnowledgeBaseUploadResponse(
            status="success",
            message="所有文件解析成功",
            successful_files=successful_files,
            failed_files=[],
            total_files=len(files),
        )

    if successful_files:
        return KnowledgeBaseUploadResponse(
            status="partial_success",
            message=(
                f"部分文件解析成功，{len(successful_files)} 个成功，"
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
            "message": "所有文件解析失败",
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
