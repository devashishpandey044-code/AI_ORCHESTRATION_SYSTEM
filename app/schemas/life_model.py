import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import LifeModelSource


class Provenance(enum.StrEnum):
    STATED = "stated"  # the user said it
    BELIEF = "belief"  # the user's own belief or opinion about themselves
    INFERRED = "inferred"  # the model's guess; never treated as a fact


class ModelItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: str = Field(min_length=1, max_length=300)
    provenance: Provenance = Provenance.STATED
    evidence: str | None = Field(default=None, max_length=300)  # the user's own words


class LifeModelData(BaseModel):
    """What the system knows about the user's life. Unknown fields are rejected, not ignored."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    current_situation: str | None = Field(default=None, max_length=500)
    vision: list[ModelItem] = Field(default_factory=list, max_length=10)
    values: list[ModelItem] = Field(default_factory=list, max_length=10)
    priorities: list[ModelItem] = Field(default_factory=list, max_length=10)
    resources: list[ModelItem] = Field(default_factory=list, max_length=10)
    concerns: list[ModelItem] = Field(default_factory=list, max_length=10)


class LifeModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    source: LifeModelSource
    data: LifeModelData
    created_at: datetime


class LifeModelVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    source: LifeModelSource
    created_at: datetime


class LifeModelUpdate(BaseModel):
    data: LifeModelData
