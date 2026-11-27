import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.models import ExperimentStatus
from app.methods.schema import Difficulty, EvidenceLevel, ScheduleKind
from app.methods.taxonomy import RoadblockType
from app.schemas.safety import SafetyResponse


class MethodSummary(BaseModel):
    slug: str
    title: str
    summary: str
    targets: list[RoadblockType]
    evidence_level: EvidenceLevel


class MethodOut(MethodSummary):
    target_behavior: str
    difficulty: Difficulty
    duration_minutes: int
    schedule_kind: ScheduleKind
    steps: list[str]
    ideal_context: str
    contraindications: list[str]
    measurement: str
    evidence_note: str
    sources: list[str]
    escalation_note: str | None
    sources_reviewed: bool  # True once a person has checked the citations


class SuggestedMethod(MethodOut):
    matched_roadblocks: list[RoadblockType]
    reasons: list[str]


class SuggestRequest(BaseModel):
    roadblocks: list[RoadblockType] = Field(min_length=1, max_length=4)
    situation: str | None = Field(default=None, max_length=1000)


class SuggestResponse(BaseModel):
    """Suggestions, or a safety response. Nothing is saved either way."""

    suggestions: list[SuggestedMethod] = Field(default_factory=list)
    already_trying: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    care_note: str | None = None
    safety: SafetyResponse | None = None


class StartExperiment(BaseModel):
    method_slug: str = Field(min_length=3, max_length=60)
    roadblock: RoadblockType


class EndExperiment(BaseModel):
    outcome: ExperimentStatus
    rating: int | None = Field(default=None, ge=1, le=5)

    @field_validator("outcome")
    @classmethod
    def _must_end(cls, value: ExperimentStatus) -> ExperimentStatus:
        if value == ExperimentStatus.ACTIVE:
            raise ValueError("outcome must be completed or abandoned")
        return value


class ExperimentOut(BaseModel):
    id: uuid.UUID
    method_slug: str
    method_title: str | None  # None if the method was removed from the library
    roadblock: str
    status: ExperimentStatus
    rating: int | None
    started_at: datetime
    ended_at: datetime | None
