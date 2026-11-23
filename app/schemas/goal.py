import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import GoalHorizon, GoalSource, GoalStatus


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    horizon: GoalHorizon
    parent_id: uuid.UUID | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: GoalSource = GoalSource.STATED
    due_date: date | None = None


class GoalUpdate(BaseModel):
    """Partial update. Horizon is intentionally not editable (it would break the hierarchy)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: GoalStatus | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    due_date: date | None = None
    parent_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _no_null_required_fields(self) -> "GoalUpdate":
        for name in ("title", "status", "confidence"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str
    description: str | None
    horizon: GoalHorizon
    status: GoalStatus
    source: GoalSource
    confidence: float
    due_date: date | None
    last_reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GoalTreeOut(GoalOut):
    children: list["GoalTreeOut"] = Field(default_factory=list)
