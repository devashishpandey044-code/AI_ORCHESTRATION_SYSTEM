from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.db.models import LifeModelSource, LifeModelVersion
from app.llm.base import LLMProvider, LLMProviderError, LLMValidationError
from app.llm.factory import get_llm_provider
from app.schemas.life_model import LifeModelData, LifeModelVersionOut
from app.schemas.onboarding import OnboardingConfirm, OnboardingProposal, OnboardingRequest
from app.services import life_model as life_model_service
from app.services.onboarding import count_recent_calls, propose_life_model

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

LLMDep = Annotated[LLMProvider, Depends(get_llm_provider)]


@router.post("/propose", response_model=OnboardingProposal)
def propose(
    payload: OnboardingRequest, user: CurrentUser, db: DbSession, provider: LLMDep
) -> OnboardingProposal:
    """Turn the user's own words into a proposed Life Model. Saves nothing."""
    if count_recent_calls(db, user.id) >= get_settings().onboarding_daily_limit:
        raise HTTPException(status_code=429, detail="Daily onboarding limit reached. Try tomorrow.")
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
    return life_model_service.save_new_version(
        db, user.id, payload.data, LifeModelSource.ONBOARDING
    )
