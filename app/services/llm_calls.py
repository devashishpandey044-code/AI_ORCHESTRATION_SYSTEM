import uuid

from sqlalchemy.orm import Session

from app.db.models import LLMCall
from app.llm.structured import StructuredResult


def record_llm_call(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    purpose: str,
    provider: str,
    model: str,
    prompt_version: str,
    attempts: int,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    success: bool,
    error: str | None = None,
) -> LLMCall:
    """Log call metadata only. Never pass prompt or response text here."""
    row = LLMCall(
        user_id=user_id,
        purpose=purpose,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        attempts=attempts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        success=success,
        error=error[:500] if error else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def record_structured_result(
    db: Session, *, user_id: uuid.UUID | None, purpose: str, result: StructuredResult
) -> LLMCall:
    return record_llm_call(
        db,
        user_id=user_id,
        purpose=purpose,
        provider=result.provider,
        model=result.model,
        prompt_version=result.prompt_version,
        attempts=result.attempts,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        success=True,
    )
