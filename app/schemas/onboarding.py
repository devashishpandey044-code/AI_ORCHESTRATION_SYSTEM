from pydantic import BaseModel, Field

from app.schemas.life_model import LifeModelData
from app.schemas.safety import SafetyResponse


class OnboardingRequest(BaseModel):
    # min_length is 1 on purpose: the safety check must see even very short messages.
    # The real minimum is enforced in the route AFTER the safety check.
    text: str = Field(min_length=1, max_length=4000)


class OnboardingProposal(BaseModel):
    """Either a proposal, or a safety response. Never both. Nothing is saved either way."""

    proposal: LifeModelData | None = None
    notes: list[str] = Field(default_factory=list)
    safety: SafetyResponse | None = None


class OnboardingConfirm(BaseModel):
    data: LifeModelData  # the final version, after any edits by the user
