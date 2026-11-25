"""method embeddings

Revision ID: 297d5dba43a1
Revises: c6c343e17ed7
Create Date: 2026-11-24 07:56:25.987118
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '297d5dba43a1'
down_revision: str | None = 'c6c343e17ed7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE method_embeddings (
            slug text PRIMARY KEY,
            content_hash text NOT NULL,
            model text NOT NULL,
            embedding vector(256) NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE method_embeddings")
