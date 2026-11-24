from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.db.models import LifeModelVersion
from app.schemas.life_model import LifeModelVersionOut
from app.services import life_model as life_model_service

router = APIRouter(prefix="/life-model", tags=["life-model"])


@router.get("", response_model=LifeModelVersionOut)
def get_my_life_model(user: CurrentUser, db: DbSession) -> LifeModelVersion:
    row = life_model_service.get_current(db, user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="No life model yet. Complete onboarding first.")
    return row
