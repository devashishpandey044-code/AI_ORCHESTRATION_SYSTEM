"""Read a user's own model-call records for a time window. Read only: nothing is written."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LLMCall
from app.usage.summary import CallRow


def load_call_rows(db: Session, user_id: uuid.UUID, since: datetime) -> list[CallRow]:
    """The user's calls from `since` on. Raises UsageError if a stored row is damaged."""
    records = db.scalars(
        select(LLMCall).where(LLMCall.user_id == user_id, LLMCall.created_at >= since)
    ).all()
    return [
        CallRow(
            purpose=record.purpose,
            model=record.model,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            latency_ms=record.latency_ms,
            success=record.success,
            attempts=record.attempts,
        )
        for record in records
    ]
