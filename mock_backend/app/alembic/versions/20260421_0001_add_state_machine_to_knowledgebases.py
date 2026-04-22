"""add state machine fields to knowledgebases

Revision ID: 20260421_0001
Revises: 20260420_0001
Create Date: 2026-04-21
"""

from alembic import op


revision = "20260421_0001"
down_revision = "20260420_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加状态机字段
    op.execute(
        """
        ALTER TABLE knowledgebases
            ADD COLUMN IF NOT EXISTS retry_count SMALLINT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS chunk_count INTEGER,
            ADD COLUMN IF NOT EXISTS indexed_count INTEGER,
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP
        """
    )

    # 修改 status 字段默认值为 'uploaded'
    op.execute(
        """
        ALTER TABLE knowledgebases
            ALTER COLUMN status SET DEFAULT 'uploaded'
        """
    )

    # 为 status 字段添加索引以提升查询性能
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledgebases_status
        ON knowledgebases (status)
        """
    )

    # 更新现有记录：将 'completed' 状态的记录补充完成时间
    op.execute(
        """
        UPDATE knowledgebases
        SET
            started_at = COALESCE(started_at, created_at),
            completed_at = COALESCE(completed_at, created_at)
        WHERE status = 'completed'
          AND completed_at IS NULL
        """
    )


def downgrade() -> None:
    # 删除索引
    op.execute("DROP INDEX IF EXISTS ix_knowledgebases_status")

    # 恢复 status 默认值
    op.execute(
        """
        ALTER TABLE knowledgebases
            ALTER COLUMN status SET DEFAULT 'completed'
        """
    )

    # 删除状态机字段
    op.execute(
        """
        ALTER TABLE knowledgebases
            DROP COLUMN IF EXISTS completed_at,
            DROP COLUMN IF EXISTS started_at,
            DROP COLUMN IF EXISTS indexed_count,
            DROP COLUMN IF EXISTS chunk_count,
            DROP COLUMN IF EXISTS retry_count
        """
    )
