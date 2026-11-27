from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.constraint import ConstraintOut
from app.schemas.goal import GoalOut
from app.schemas.life_model import LifeModelVersionOut
from app.schemas.methods import ExperimentOut
from app.schemas.user import UserOut


class UserExport(BaseModel):
    exported_at: datetime
    user: UserOut
    goals: list[GoalOut]
    constraints: list[ConstraintOut]
    life_model_versions: list[LifeModelVersionOut]
    method_experiments: list[ExperimentOut]
    plans: list[dict[str, Any]] = Field(default_factory=list)
    checkins: list[dict[str, Any]] = Field(default_factory=list)
