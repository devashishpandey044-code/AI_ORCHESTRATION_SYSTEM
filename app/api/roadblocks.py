from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.llm.base import LLMProvider, LLMProviderError, LLMValidationError
from app.llm.factory import get_llm_provider
from app.roadblocks.detector import PURPOSE, detect_roadblocks
from app.safety.crisis import check_text
from app.safety.response import build_support_response
from app.schemas.roadblocks import DetectRequest, DetectResponse
from app.schemas.safety import SafetyResponse, SupportResourceOut
from app.services.onboarding import count_recent_calls
from app.services.safety import record_safety_event

router = APIRouter(prefix="/roadblocks", tags=["roadblocks"])

LLMDep = Annotated[LLMProvider, Depends(get_llm_provider)]

MIN_TEXT_LENGTH = 20


@router.post("/detect", response_model=DetectResponse)
def detect(
    payload: DetectRequest, user: CurrentUser, db: DbSession, provider: LLMDep
) -> DetectResponse:
    """Find what is getting in the way, from the user's words and/or activity. Saves nothing."""
    text = (payload.text or "").strip()
    if text:
        # 1. Safety first, before length rules, rate limits and any model call.
        check = check_text(text)
        if check.triggered:
            record_safety_event(db, surface="roadblocks", check=check)
            message, resources = build_support_response(get_settings().crisis_region)
            return DetectResponse(
                safety=SafetyResponse(
                    category=check.category,
                    message=message,
                    resources=[SupportResourceOut.model_validate(r) for r in resources],
                )
            )
        # 2. Ordinary validation and limits.
        if len(text) < MIN_TEXT_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"Please write at least {MIN_TEXT_LENGTH} characters or send activity data.",
            )
        if count_recent_calls(db, user.id, PURPOSE) >= get_settings().roadblock_daily_limit:
            raise HTTPException(status_code=429, detail="Daily limit reached. Try tomorrow.")

    try:
        result = detect_roadblocks(db, provider, user.id, text, payload.execution)
    except LLMValidationError:
        raise HTTPException(
            status_code=502, detail="The assistant could not produce a valid answer. Try again."
        ) from None
    except LLMProviderError:
        raise HTTPException(
            status_code=503, detail="The assistant is unavailable right now. Try again later."
        ) from None
    return DetectResponse(
        roadblocks=result.roadblocks, notes=result.notes, care_note=result.care_note
    )
