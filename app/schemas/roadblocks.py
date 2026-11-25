import enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.methods.taxonomy import RoadblockType
from app.schemas.safety import SafetyResponse


class Strength(enum.StrEnum):
    STRONG = "strong"
    POSSIBLE = "possible"


class SignalSource(enum.StrEnum):
    DATA = "data"  # from the user's own activity numbers
    USER_WORDS = "user_words"  # the model quoted words that really are in the user's text
    MODEL_GUESS = "model_guess"  # the model suggested it without a verifiable quote


class Signal(BaseModel):
    source: SignalSource
    detail: str


class DetectedRoadblock(BaseModel):
    roadblock: RoadblockType
    description: str
    strength: Strength
    sensitive: bool
    signals: list[Signal]


class ExecutionSummary(BaseModel):
    """A summary of recent activity. Later it will be computed from stored plans and check-ins."""

    model_config = ConfigDict(extra="forbid")

    days_covered: int = Field(ge=1, le=90)
    focus_blocks_planned: int = Field(default=0, ge=0, le=1000)
    focus_blocks_completed: int = Field(default=0, ge=0, le=1000)
    unplanned_phone_checks: int = Field(default=0, ge=0, le=10000)
    tasks_planned: int = Field(default=0, ge=0, le=1000)
    tasks_completed: int = Field(default=0, ge=0, le=1000)
    tasks_postponed_3_plus: int = Field(default=0, ge=0, le=1000)
    days_over_capacity: int = Field(default=0, ge=0, le=90)
    avg_actual_to_estimate_ratio: float | None = Field(default=None, gt=0, le=10)
    energy_ratings: list[int] = Field(default_factory=list, max_length=90)
    low_energy_streak_days: int = Field(default=0, ge=0, le=90)

    @model_validator(mode="after")
    def _consistent(self) -> "ExecutionSummary":
        if self.focus_blocks_completed > self.focus_blocks_planned:
            raise ValueError("focus_blocks_completed cannot exceed focus_blocks_planned")
        if self.tasks_completed > self.tasks_planned:
            raise ValueError("tasks_completed cannot exceed tasks_planned")
        if self.days_over_capacity > self.days_covered:
            raise ValueError("days_over_capacity cannot exceed days_covered")
        if self.low_energy_streak_days > self.days_covered:
            raise ValueError("low_energy_streak_days cannot exceed days_covered")
        if len(self.energy_ratings) > self.days_covered:
            raise ValueError("there cannot be more energy_ratings than days_covered")
        if any(rating < 1 or rating > 5 for rating in self.energy_ratings):
            raise ValueError("energy_ratings must be between 1 and 5")
        return self


class DetectRequest(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    execution: ExecutionSummary | None = None

    @model_validator(mode="after")
    def _something_to_analyse(self) -> "DetectRequest":
        has_text = bool(self.text and self.text.strip())
        if not has_text and self.execution is None:
            raise ValueError("Provide text, execution data, or both.")
        return self


class DetectResponse(BaseModel):
    """Either detected roadblocks, or a safety response. Nothing is saved either way."""

    roadblocks: list[DetectedRoadblock] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    care_note: str | None = None
    safety: SafetyResponse | None = None
