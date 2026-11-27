import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.db.models import ExperimentStatus, MethodExperiment, User
from app.methods.loader import get_library, get_method
from app.retrieval.runtime import RetrievalIndex, get_index
from app.safety.crisis import check_text
from app.schemas.methods import (
    EndExperiment,
    ExperimentOut,
    MethodOut,
    MethodSummary,
    StartExperiment,
    SuggestRequest,
    SuggestResponse,
)
from app.services.methods import experiment_to_out, method_to_out, suggest_methods
from app.services.safety import safety_stop

router = APIRouter(prefix="/methods", tags=["methods"])

IndexDep = Annotated[RetrievalIndex, Depends(get_index)]

_DUPLICATE = "You are already trying this method."

# NOTE: the fixed paths (/suggest, /experiments) are declared BEFORE /{slug}, or FastAPI would
# treat the word "experiments" as a method slug.


@router.post("/suggest", response_model=SuggestResponse)
def suggest(
    payload: SuggestRequest, user: CurrentUser, db: DbSession, index: IndexDep
) -> SuggestResponse:
    """Suggest up to two methods for the given roadblocks. Saves nothing, calls no model."""
    situation = (payload.situation or "").strip()
    if situation:
        check = check_text(situation)
        if check.triggered:
            return SuggestResponse(safety=safety_stop(db, surface="methods", check=check))
    return suggest_methods(db, user.id, index, payload.roadblocks, situation)


@router.get("", response_model=list[MethodSummary])
def list_library(user: CurrentUser) -> list[MethodSummary]:
    return [
        MethodSummary(
            slug=m.slug,
            title=m.title,
            summary=m.summary,
            targets=list(m.targets),
            evidence_level=m.evidence_level,
        )
        for m in sorted(get_library(), key=lambda m: m.title)
    ]


def _owned_experiment(db: DbSession, user: User, experiment_id: uuid.UUID) -> MethodExperiment:
    row = db.scalar(
        select(MethodExperiment).where(
            MethodExperiment.id == experiment_id, MethodExperiment.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return row


@router.post("/experiments", response_model=ExperimentOut, status_code=201)
def start_experiment(payload: StartExperiment, user: CurrentUser, db: DbSession) -> ExperimentOut:
    method = get_method(payload.method_slug)
    if method is None:
        raise HTTPException(status_code=404, detail="Unknown method")
    if payload.roadblock not in method.targets:
        raise HTTPException(
            status_code=422,
            detail=f"'{method.title}' is not meant for {payload.roadblock.value}.",
        )
    active = db.scalars(
        select(MethodExperiment.method_slug).where(
            MethodExperiment.user_id == user.id,
            MethodExperiment.status == ExperimentStatus.ACTIVE,
        )
    ).all()
    if payload.method_slug in active:
        raise HTTPException(status_code=409, detail=_DUPLICATE)
    if len(active) >= get_settings().max_active_experiments:
        raise HTTPException(
            status_code=409,
            detail="You already have the maximum number of active experiments. "
            "Finish or stop one first.",
        )
    row = MethodExperiment(
        user_id=user.id,
        method_slug=payload.method_slug,
        roadblock=payload.roadblock.value,
        status=ExperimentStatus.ACTIVE,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=_DUPLICATE) from None
    db.refresh(row)
    return experiment_to_out(row)


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments(
    user: CurrentUser,
    db: DbSession,
    status: ExperimentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ExperimentOut]:
    stmt = select(MethodExperiment).where(MethodExperiment.user_id == user.id)
    if status is not None:
        stmt = stmt.where(MethodExperiment.status == status)
    stmt = stmt.order_by(MethodExperiment.started_at.desc(), MethodExperiment.id)
    rows = db.scalars(stmt.limit(limit).offset(offset))
    return [experiment_to_out(row) for row in rows]


@router.post("/experiments/{experiment_id}/end", response_model=ExperimentOut)
def end_experiment(
    experiment_id: uuid.UUID, payload: EndExperiment, user: CurrentUser, db: DbSession
) -> ExperimentOut:
    row = _owned_experiment(db, user, experiment_id)
    if row.status != ExperimentStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="This experiment has already ended.")
    row.status = payload.outcome
    row.rating = payload.rating
    row.ended_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return experiment_to_out(row)


@router.get("/{slug}", response_model=MethodOut)
def get_library_method(slug: str, user: CurrentUser) -> MethodOut:
    method = get_method(slug)
    if method is None:
        raise HTTPException(status_code=404, detail="Method not found")
    return method_to_out(method)
