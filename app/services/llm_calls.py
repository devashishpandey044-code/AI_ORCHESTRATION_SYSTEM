import time
import uuid

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import LLMCall
from app.llm.base import LLMProvider, LLMProviderError, LLMValidationError
from app.llm.structured import StructuredResult, complete_structured


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


def run_logged_structured[T: BaseModel](
    db: Session,
    provider: LLMProvider,
    schema: type[T],
    *,
    user_id: uuid.UUID | None,
    purpose: str,
    system: str,
    user: str,
    prompt_version: str,
    max_tokens: int = 1000,
) -> StructuredResult[T]:
    """Run a structured model call and log it (success or failure) with metadata only."""
    started = time.perf_counter()
    try:
        result = complete_structured(
            provider,
            schema,
            system=system,
            user=user,
            prompt_version=prompt_version,
            max_tokens=max_tokens,
        )
    except LLMValidationError as exc:
        record_llm_call(
            db,
            user_id=user_id,
            purpose=purpose,
            provider=provider.name,
            model=exc.model or "unknown",
            prompt_version=prompt_version,
            attempts=exc.attempts,
            input_tokens=exc.input_tokens,
            output_tokens=exc.output_tokens,
            latency_ms=(time.perf_counter() - started) * 1000,
            success=False,
            error="validation_failed",
        )
        raise
    except LLMProviderError as exc:
        record_llm_call(
            db,
            user_id=user_id,
            purpose=purpose,
            provider=provider.name,
            model="unknown",
            prompt_version=prompt_version,
            attempts=1,
            input_tokens=0,
            output_tokens=0,
            latency_ms=(time.perf_counter() - started) * 1000,
            success=False,
            error=str(exc),
        )
        raise
    record_structured_result(db, user_id=user_id, purpose=purpose, result=result)
    return result
