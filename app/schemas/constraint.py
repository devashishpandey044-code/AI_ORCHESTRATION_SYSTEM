import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import ConstraintKind


class ConstraintCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: ConstraintKind
    days_of_week: list[int] = Field(default_factory=list)  # 0=Mon .. 6=Sun
    start_time: time | None = None
    end_time: time | None = None
    max_minutes_per_day: int | None = Field(default=None, ge=1, le=1440)
    is_hard: bool = True
    active: bool = True

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days_of_week values must be between 0 (Mon) and 6 (Sun)")
        return sorted(set(v))

    @model_validator(mode="after")
    def _check_shape(self) -> "ConstraintCreate":
        if self.kind == ConstraintKind.CAPACITY_LIMIT:
            if self.max_minutes_per_day is None:
                raise ValueError("capacity_limit requires max_minutes_per_day")
            if not self.days_of_week:
                self.days_of_week = list(range(7))
            return self

        if not self.days_of_week:
            raise ValueError(f"{self.kind.value} requires days_of_week")
        if self.start_time is None or self.end_time is None:
            raise ValueError(f"{self.kind.value} requires start_time and end_time")
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must differ")
        if self.kind == ConstraintKind.FIXED_COMMITMENT and self.start_time > self.end_time:
            raise ValueError("start_time must be before end_time for a fixed commitment")
        # sleep may legitimately cross midnight (e.g. 23:00 -> 07:00)
        return self


class ConstraintUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    kind: ConstraintKind | None = None
    days_of_week: list[int] | None = None
    start_time: time | None = None
    end_time: time | None = None
    max_minutes_per_day: int | None = Field(default=None, ge=1, le=1440)
    is_hard: bool | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def _no_null_required_fields(self) -> "ConstraintUpdate":
        for name in ("title", "kind", "days_of_week", "is_hard", "active"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ConstraintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    kind: ConstraintKind
    days_of_week: list[int]
    start_time: time | None
    end_time: time | None
    max_minutes_per_day: int | None
    is_hard: bool
    active: bool
    created_at: datetime
    updated_at: datetime
