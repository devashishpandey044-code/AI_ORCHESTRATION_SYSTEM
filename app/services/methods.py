import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExperimentStatus, MethodExperiment
from app.methods.loader import get_method
from app.methods.schema import Method
from app.methods.taxonomy import SENSITIVE, RoadblockType
from app.retrieval.retriever import Retrieved, retrieve_methods
from app.retrieval.runtime import RetrievalIndex
from app.roadblocks.detector import CARE_NOTE
from app.schemas.methods import ExperimentOut, MethodOut, SuggestedMethod, SuggestResponse

MAX_SUGGESTIONS = 2
LIKED_MIN_RATING = 4
DISLIKED_MAX_RATING = 2


def method_to_out(method: Method) -> MethodOut:
    data = method.model_dump(exclude={"reviewed_on"})
    return MethodOut(**data, sources_reviewed=method.reviewed_on is not None)


def experiment_to_out(row: MethodExperiment) -> ExperimentOut:
    method = get_method(row.method_slug)
    return ExperimentOut(
        id=row.id,
        method_slug=row.method_slug,
        method_title=method.title if method else None,
        roadblock=row.roadblock,
        status=row.status,
        rating=row.rating,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


@dataclass(frozen=True)
class MethodHistory:
    active: frozenset[str]
    demote: frozenset[str]  # abandoned, or finished with a rating of 1 or 2
    liked: frozenset[str]  # finished with a rating of 4 or 5


def load_history(db: Session, user_id: uuid.UUID) -> MethodHistory:
    stmt = select(MethodExperiment).where(MethodExperiment.user_id == user_id)
    rows = db.scalars(stmt).all()
    active = {row.method_slug for row in rows if row.status == ExperimentStatus.ACTIVE}
    ended = sorted(
        (row for row in rows if row.status != ExperimentStatus.ACTIVE),
        key=lambda row: row.ended_at or row.started_at,
    )
    verdict: dict[str, str] = {}  # the most recent finished attempt decides
    for row in ended:
        if row.status == ExperimentStatus.ABANDONED:
            verdict[row.method_slug] = "demote"
        elif row.rating is not None and row.rating <= DISLIKED_MAX_RATING:
            verdict[row.method_slug] = "demote"
        elif row.rating is not None and row.rating >= LIKED_MIN_RATING:
            verdict[row.method_slug] = "liked"
        else:
            verdict[row.method_slug] = "neutral"
    return MethodHistory(
        active=frozenset(active),
        demote=frozenset(s for s, v in verdict.items() if v == "demote" and s not in active),
        liked=frozenset(s for s, v in verdict.items() if v == "liked" and s not in active),
    )


def select_methods(
    candidates: Sequence[Retrieved],
    active: set[str],
    demote: set[str],
    k: int = MAX_SUGGESTIONS,
) -> tuple[list[Retrieved], list[str], list[str]]:
    """Pick up to k methods. Returns (chosen, already_trying, demoted_but_used)."""
    already_trying = [c.slug for c in candidates if c.slug in active]
    available = [c for c in candidates if c.slug not in active]
    preferred = [c for c in available if c.slug not in demote]
    demoted = [c for c in available if c.slug in demote]
    chosen = (preferred + demoted)[:k]
    used_demoted = [c.slug for c in chosen if c.slug in demote]
    return chosen, already_trying, used_demoted


def build_reasons(method: Method, item: Retrieved, liked: bool) -> list[str]:
    names = ", ".join(r.value.replace("_", " ") for r in item.matched)
    reasons = [
        f"Targets {names}.",
        f"Evidence level: {method.evidence_level.value}.",
        f"About {method.duration_minutes} minutes, {method.difficulty.value} to start.",
    ]
    if liked:
        reasons.append("You rated this helpful before.")
    return reasons


def suggest_methods(
    db: Session,
    user_id: uuid.UUID,
    index: RetrievalIndex,
    roadblocks: Sequence[RoadblockType],
    situation: str,
) -> SuggestResponse:
    candidates = retrieve_methods(
        roadblocks=list(dict.fromkeys(roadblocks)),
        situation=situation,
        embedder=index.embedder,
        store=index.store,
        library=index.library,
        k=max(1, len(index.library)),
    )
    history = load_history(db, user_id)
    chosen, trying, repeated = select_methods(candidates, set(history.active), set(history.demote))
    by_slug = {m.slug: m for m in index.library}

    suggestions: list[SuggestedMethod] = []
    for item in chosen:
        method = by_slug[item.slug]
        suggestions.append(
            SuggestedMethod(
                **method_to_out(method).model_dump(),
                matched_roadblocks=list(item.matched),
                reasons=build_reasons(method, item, item.slug in history.liked),
            )
        )

    notes: list[str] = []
    if not candidates:
        notes.append("No methods in the library target these roadblocks yet.")
    elif not chosen:
        notes.append("You are already trying every method that matches.")
    for slug in repeated:
        notes.append(
            f"'{by_slug[slug].title}' is shown again only because nothing else fits, "
            "and you did not find it helpful before."
        )
    sensitive = any(set(by_slug[item.slug].targets) & SENSITIVE for item in chosen)
    return SuggestResponse(
        suggestions=suggestions,
        already_trying=trying,
        notes=notes,
        care_note=CARE_NOTE if sensitive else None,
    )
