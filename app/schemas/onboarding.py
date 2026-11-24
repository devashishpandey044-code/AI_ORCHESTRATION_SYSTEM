from pydantic import BaseModel, Field

from app.schemas.life_model import LifeModelData


class OnboardingRequest(BaseModel):
    text: str = Field(min_length=20, max_length=4000)


class OnboardingProposal(BaseModel):
    """A proposal only. Nothing is saved until the user confirms it."""

    proposal: LifeModelData
    notes: list[str]


class OnboardingConfirm(BaseModel):
    data: LifeModelData  # the final version, after any edits by the user
