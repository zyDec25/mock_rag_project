"""
文档上传状态机管理服务
实现文档入库的状态流转和重试机制
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from models.knowledgebase import KnowledgeBase


class DocumentStatus(str, Enum):
    """文档处理状态枚举"""
    UPLOADED = "uploaded"      # 文件已落盘，等待处理
    PARSING = "parsing"        # 正在解析文档内容
    CHUNKING = "chunking"      # 正在分块和分词
    EMBEDDING = "embedding"    # 正在生成向量
    INDEXING = "indexing"      # 正在写入 Elasticsearch
    COMPLETED = "completed"    # 全流程成功
    FAILED = "failed"          # 处理失败


class DocumentStateMachine:
    """文档状态机管理器"""

    MAX_RETRY_COUNT = 3

    # 状态转换规则
    VALID_TRANSITIONS = {
        DocumentStatus.UPLOADED: [DocumentStatus.PARSING, DocumentStatus.FAILED],
        DocumentStatus.PARSING: [DocumentStatus.CHUNKING, DocumentStatus.FAILED],
        DocumentStatus.CHUNKING: [DocumentStatus.EMBEDDING, DocumentStatus.FAILED],
        DocumentStatus.EMBEDDING: [DocumentStatus.INDEXING, DocumentStatus.FAILED],
        DocumentStatus.INDEXING: [DocumentStatus.COMPLETED, DocumentStatus.FAILED],
        DocumentStatus.FAILED: [DocumentStatus.PARSING],  # 允许重试
        DocumentStatus.COMPLETED: [],  # 终态
    }

    def __init__(self, db: Session):
        self.db = db

    def transition_to(
        self,
        document: KnowledgeBase,
        new_status: DocumentStatus,
        error_message: Optional[str] = None,
        chunk_count: Optional[int] = None,
        indexed_count: Optional[int] = None,
    ) -> bool:
        """
        状态转换

        Args:
            document: 文档记录
            new_status: 目标状态
            error_message: 错误信息（失败时）
            chunk_count: 分块数量
            indexed_count: 已索引数量

        Returns:
            是否转换成功
        """
        current_status = DocumentStatus(document.status)

        # 验证状态转换是否合法
        if new_status not in self.VALID_TRANSITIONS.get(current_status, []):
            raise ValueError(
                f"非法状态转换: {current_status} -> {new_status}"
            )

        # 如果是失败状态，检查重试次数
        if new_status == DocumentStatus.FAILED:
            if document.retry_count >= self.MAX_RETRY_COUNT:
                document.status = DocumentStatus.FAILED.value
                document.error_message = f"超过最大重试次数({self.MAX_RETRY_COUNT}): {error_message}"
                document.completed_at = datetime.now()
                self.db.commit()
                return False

            document.retry_count += 1
            document.error_message = error_message

        # 更新状态
        document.status = new_status.value

        # 记录开始时间（第一次进入处理流程）
        if new_status == DocumentStatus.PARSING and document.started_at is None:
            document.started_at = datetime.now()

        # 记录完成时间
        if new_status in (DocumentStatus.COMPLETED, DocumentStatus.FAILED):
            document.completed_at = datetime.now()

        # 更新统计信息
        if chunk_count is not None:
            document.chunk_count = chunk_count
        if indexed_count is not None:
            document.indexed_count = indexed_count

        self.db.commit()
        return True

    def start_parsing(self, document: KnowledgeBase) -> bool:
        """开始解析"""
        return self.transition_to(document, DocumentStatus.PARSING)

    def start_chunking(self, document: KnowledgeBase) -> bool:
        """开始分块"""
        return self.transition_to(document, DocumentStatus.CHUNKING)

    def start_embedding(self, document: KnowledgeBase, chunk_count: int) -> bool:
        """开始向量化"""
        return self.transition_to(
            document,
            DocumentStatus.EMBEDDING,
            chunk_count=chunk_count
        )

    def start_indexing(self, document: KnowledgeBase) -> bool:
        """开始索引"""
        return self.transition_to(document, DocumentStatus.INDEXING)

    def mark_completed(self, document: KnowledgeBase, indexed_count: int) -> bool:
        """标记完成"""
        return self.transition_to(
            document,
            DocumentStatus.COMPLETED,
            indexed_count=indexed_count
        )

    def mark_failed(
        self,
        document: KnowledgeBase,
        error_message: str,
        current_stage: Optional[DocumentStatus] = None
    ) -> bool:
        """
        标记失败

        Args:
            document: 文档记录
            error_message: 错误信息
            current_stage: 当前所在阶段（用于重试时恢复）
        """
        success = self.transition_to(
            document,
            DocumentStatus.FAILED,
            error_message=error_message
        )

        # 如果还可以重试，记录当前阶段以便恢复
        if success and document.retry_count < self.MAX_RETRY_COUNT:
            if current_stage:
                document.error_message = f"[{current_stage.value}] {error_message}"
                self.db.commit()

        return success

    def can_retry(self, document: KnowledgeBase) -> bool:
        """检查是否可以重试"""
        return (
            document.status == DocumentStatus.FAILED.value
            and document.retry_count < self.MAX_RETRY_COUNT
        )

    def retry(self, document: KnowledgeBase) -> bool:
        """重试失败的文档"""
        if not self.can_retry(document):
            return False

        # 重置到 parsing 阶段
        document.status = DocumentStatus.PARSING.value
        document.error_message = None
        document.started_at = datetime.now()
        document.completed_at = None
        self.db.commit()
        return True

    def get_status_summary(self, user_id: str) -> dict:
        """获取用户文档状态统计"""
        from sqlalchemy import func

        result = (
            self.db.query(
                KnowledgeBase.status,
                func.count(KnowledgeBase.id).label("count")
            )
            .filter(KnowledgeBase.user_id == user_id)
            .group_by(KnowledgeBase.status)
            .all()
        )

        return {row.status: row.count for row in result}
