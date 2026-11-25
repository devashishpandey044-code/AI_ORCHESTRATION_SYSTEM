from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.db.models import LifeModelSource, LifeModelVersion
from app.llm.base import LLMProvider, LLMProviderError, LLMValidationError
from app.llm.factory import get_llm_provider
from app.safety.crisis import check_text
from app.safety.response import build_support_response
from app.schemas.life_model import LifeModelData, LifeModelVersionOut
from app.schemas.onboarding import OnboardingConfirm, OnboardingProposal, OnboardingRequest
from app.schemas.safety import SafetyResponse, SupportResourceOut
from app.services import life_model as life_model_service
from app.services.onboarding import count_recent_calls, propose_life_model
from app.services.safety import record_safety_event

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

LLMDep = Annotated[LLMProvider, Depends(get_llm_provider)]

MIN_TEXT_LENGTH = 20


@router.post("/propose", response_model=OnboardingProposal)
def propose(
    payload: OnboardingRequest, user: CurrentUser, db: DbSession, provider: LLMDep
) -> OnboardingProposal:
    """Turn the user's own words into a proposed Life Model. Saves nothing."""
    # 1. Safety first, before length rules, rate limits and any model call.
    check = check_text(payload.text)
    if check.triggered:
        record_safety_event(db, surface="onboarding", check=check)
        message, resources = build_support_response(get_settings().crisis_region)
        return OnboardingProposal(
            safety=SafetyResponse(
                category=check.category,
                message=message,
                resources=[SupportResourceOut.model_validate(r) for r in resources],
            )
        )

    # 2. Ordinary validation and limits.
    if len(payload.text.strip()) < MIN_TEXT_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Please write at least {MIN_TEXT_LENGTH} characters "
                "so there is enough to work with."
            ),
        )
    if count_recent_calls(db, user.id) >= get_settings().onboarding_daily_limit:
        raise HTTPException(status_code=429, detail="Daily onboarding limit reached. Try tomorrow.")

    # 3. Only now does a model see the text.
    try:
        data, notes = propose_life_model(db, provider, user.id, payload.text)
    except LLMValidationError:
        raise HTTPException(
            status_code=502, detail="The assistant could not produce a valid proposal. Try again."
        ) from None
    except LLMProviderError:
        raise HTTPException(
            status_code=503, detail="The assistant is unavailable right now. Try again later."
        ) from None
    return OnboardingProposal(proposal=data, notes=notes)


@router.post("/confirm", response_model=LifeModelVersionOut, status_code=201)
def confirm(payload: OnboardingConfirm, user: CurrentUser, db: DbSession) -> LifeModelVersion:
    """Save what the user approved as a new Life Model version. The model is not involved."""
    if payload.data == LifeModelData():
        raise HTTPException(status_code=422, detail="Add at least one detail before saving.")
    try:
        return life_model_service.save_new_version(
            db, user.id, payload.data, LifeModelSource.ONBOARDING
        )
    except life_model_service.VersionConflictError:
        raise HTTPException(
            status_code=409, detail="Your life model changed elsewhere. Reload it and try again."
        ) from None
