"""expand mock backend data models

Revision ID: 20260420_0001
Revises:
Create Date: 2026-04-20
"""

from alembic import op


revision = "20260420_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledgebases (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'completed',
            error_message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledgebases_user_id "
        "ON knowledgebases (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledgebases_created_at "
        "ON knowledgebases (created_at)"
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.knowledgebase') IS NOT NULL THEN
                INSERT INTO knowledgebases (user_id, file_name, created_at, updated_at)
                SELECT
                    user_id,
                    file_name,
                    COALESCE(created_at, CURRENT_TIMESTAMP),
                    COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
                FROM knowledgebase kb
                WHERE user_id IS NOT NULL
                  AND file_name IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM knowledgebases kbs
                      WHERE kbs.user_id = kb.user_id
                        AND kbs.file_name = kb.file_name
                  );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        ALTER TABLE document_uploads
            ADD COLUMN IF NOT EXISTS parse_type VARCHAR(10) NOT NULL DEFAULT 'full',
            ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'uploaded',
            ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS error_message TEXT,
            ADD COLUMN IF NOT EXISTS error_code INTEGER,
            ADD COLUMN IF NOT EXISTS chunk_count INTEGER,
            ADD COLUMN IF NOT EXISTS indexed_count INTEGER,
            ADD COLUMN IF NOT EXISTS content_length INTEGER,
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP
        """
    )
    op.execute(
        """
        UPDATE document_uploads
        SET
            parse_type = 'quick',
            status = 'cached',
            retry_count = COALESCE(retry_count, 0),
            content_length = COALESCE(content_length, file_size),
            started_at = COALESCE(started_at, upload_time, created_at),
            completed_at = COALESCE(completed_at, upload_time, created_at),
            expires_at = COALESCE(expires_at, upload_time + INTERVAL '2 hours')
        WHERE parse_type = 'full'
          AND status = 'uploaded'
        """
    )

    op.execute(
        """
        ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed',
            ADD COLUMN IF NOT EXISTS error_message TEXT,
            ADD COLUMN IF NOT EXISTS retrieval_time_ms INTEGER,
            ADD COLUMN IF NOT EXISTS generation_time_ms INTEGER,
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP
        """
    )
    op.execute(
        """
        UPDATE messages
        SET
            status = COALESCE(status, 'completed'),
            retrieval_time_ms = COALESCE(retrieval_time_ms, 0),
            generation_time_ms = COALESCE(generation_time_ms, 0),
            started_at = COALESCE(started_at, created_at),
            completed_at = COALESCE(completed_at, created_at)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE messages
            DROP COLUMN IF EXISTS completed_at,
            DROP COLUMN IF EXISTS started_at,
            DROP COLUMN IF EXISTS generation_time_ms,
            DROP COLUMN IF EXISTS retrieval_time_ms,
            DROP COLUMN IF EXISTS error_message,
            DROP COLUMN IF EXISTS status
        """
    )
    op.execute(
        """
        ALTER TABLE document_uploads
            DROP COLUMN IF EXISTS expires_at,
            DROP COLUMN IF EXISTS completed_at,
            DROP COLUMN IF EXISTS started_at,
            DROP COLUMN IF EXISTS content_length,
            DROP COLUMN IF EXISTS indexed_count,
            DROP COLUMN IF EXISTS chunk_count,
            DROP COLUMN IF EXISTS error_code,
            DROP COLUMN IF EXISTS error_message,
            DROP COLUMN IF EXISTS retry_count,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS parse_type
        """
    )
    op.execute("DROP TABLE IF EXISTS knowledgebases")
