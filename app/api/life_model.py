from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from app.api.deps import CurrentUser, DbSession
from app.db.models import LifeModelSource, LifeModelVersion
from app.schemas.life_model import (
    LifeModelUpdate,
    LifeModelVersionOut,
    LifeModelVersionSummary,
)
from app.services import life_model as life_model_service

router = APIRouter(prefix="/life-model", tags=["life-model"])

# The upper bound keeps absurd numbers from reaching the database as an integer overflow.
VersionPath = Annotated[int, Path(ge=1, le=1_000_000)]

_CONFLICT = "Your life model changed elsewhere. Reload it and try again."


@router.get("", response_model=LifeModelVersionOut)
def get_my_life_model(user: CurrentUser, db: DbSession) -> LifeModelVersion:
    row = life_model_service.get_current(db, user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="No life model yet. Complete onboarding first.")
    return row


@router.put("", response_model=LifeModelVersionOut)
def edit_my_life_model(
    payload: LifeModelUpdate, user: CurrentUser, db: DbSession
) -> LifeModelVersion:
    """Replace the model with the user's edited copy, as a new version.

    The user is the source of truth here, so no model is involved. An edit that changes
    nothing returns the current version and creates no new one.
    """
    current = life_model_service.get_current(db, user.id)
    if current is None:
        raise HTTPException(status_code=404, detail="No life model yet. Complete onboarding first.")
    if payload.data == life_model_service.parse_data(current):
        return current
    try:
        return life_model_service.save_new_version(
            db, user.id, payload.data, LifeModelSource.USER_EDIT
        )
    except life_model_service.VersionConflictError:
        raise HTTPException(status_code=409, detail=_CONFLICT) from None


@router.get("/versions", response_model=list[LifeModelVersionSummary])
def list_my_versions(user: CurrentUser, db: DbSession) -> list[LifeModelVersion]:
    return life_model_service.list_versions(db, user.id)


@router.get("/versions/{version}", response_model=LifeModelVersionOut)
def get_my_version(version: VersionPath, user: CurrentUser, db: DbSession) -> LifeModelVersion:
    row = life_model_service.get_version(db, user.id, version)
    if row is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return row


@router.post("/versions/{version}/restore", response_model=LifeModelVersionOut, status_code=201)
def restore_my_version(version: VersionPath, user: CurrentUser, db: DbSession) -> LifeModelVersion:
    """Copy an old version into a NEW version. History is never rewritten."""
    old = life_model_service.get_version(db, user.id, version)
    if old is None:
        raise HTTPException(status_code=404, detail="Version not found")
    current = life_model_service.get_current(db, user.id)
    if current is not None and current.version == version:
        raise HTTPException(status_code=409, detail="That version is already the current one.")
    try:
        return life_model_service.save_new_version(
            db, user.id, life_model_service.parse_data(old), LifeModelSource.USER_EDIT
        )
    except life_model_service.VersionConflictError:
        raise HTTPException(status_code=409, detail=_CONFLICT) from None
