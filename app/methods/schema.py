import enum
import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.methods.taxonomy import SENSITIVE, RoadblockType

_SLUG = re.compile(r"^[a-z][a-z0-9_]{2,59}$")


class Difficulty(enum.StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class EvidenceLevel(enum.StrEnum):
    STRONG = "strong"  # repeated experiments or meta-analyses
    MODERATE = "moderate"  # some good studies, or evidence from related areas
    LIMITED = "limited"  # a few studies, small or with mixed replication
    PRACTITIONER = "practitioner"  # widely used practice without strong research


class ScheduleKind(enum.StrEnum):
    SETUP_ONCE = "setup_once"
    BEFORE_BLOCK = "before_block"  # a short action placed just before another block
    DAILY_BLOCK = "daily_block"
    WEEKLY_BLOCK = "weekly_block"
    CUE_BASED = "cue_based"  # triggered by a time, place or event


def _clean(items: list[str], what: str, min_len: int, max_len: int) -> list[str]:
    cleaned = [item.strip() for item in items]
    if any(len(item) < min_len for item in cleaned):
        raise ValueError(f"every {what} needs at least {min_len} characters")
    if any(len(item) > max_len for item in cleaned):
        raise ValueError(f"every {what} must be at most {max_len} characters")
    return cleaned


class Method(BaseModel):
    """One intervention in the methodology library. Curated by a person, never by a model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str
    title: str = Field(min_length=3, max_length=80)
    summary: str = Field(min_length=20, max_length=300)
    targets: list[RoadblockType] = Field(min_length=1, max_length=4)
    target_behavior: str = Field(min_length=5, max_length=200)
    difficulty: Difficulty
    duration_minutes: int = Field(ge=1, le=240)
    schedule_kind: ScheduleKind
    steps: list[str] = Field(min_length=3, max_length=7)
    ideal_context: str = Field(min_length=10, max_length=300)
    contraindications: list[str] = Field(min_length=1, max_length=6)
    measurement: str = Field(min_length=10, max_length=300)
    evidence_level: EvidenceLevel
    evidence_note: str = Field(min_length=10, max_length=400)
    sources: list[str] = Field(default_factory=list, max_length=5)
    escalation_note: str | None = Field(default=None, max_length=400)
    reviewed_on: date | None = None  # when a person last checked the sources

    @field_validator("slug")
    @classmethod
    def _slug_format(cls, value: str) -> str:
        if not _SLUG.match(value):
            raise ValueError("slug must be lowercase letters, digits and underscores")
        return value

    @field_validator("steps")
    @classmethod
    def _steps(cls, value: list[str]) -> list[str]:
        return _clean(value, "step", 5, 250)

    @field_validator("contraindications")
    @classmethod
    def _contraindications(cls, value: list[str]) -> list[str]:
        return _clean(value, "contraindication", 5, 250)

    @field_validator("sources")
    @classmethod
    def _sources(cls, value: list[str]) -> list[str]:
        return _clean(value, "source", 10, 400)

    @model_validator(mode="after")
    def _cross_checks(self) -> "Method":
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("targets must not repeat")
        if self.evidence_level in (EvidenceLevel.STRONG, EvidenceLevel.MODERATE):
            if not self.sources:
                raise ValueError("strong or moderate evidence needs at least one source")
        if SENSITIVE & set(self.targets):
            if not (self.escalation_note and self.escalation_note.strip()):
                raise ValueError("methods for low_energy or burnout_risk need an escalation_note")
        return self
