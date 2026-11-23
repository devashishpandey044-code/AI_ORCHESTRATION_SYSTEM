from datetime import datetime

from pydantic import BaseModel

from app.schemas.constraint import ConstraintOut
from app.schemas.goal import GoalOut
from app.schemas.user import UserOut


class UserExport(BaseModel):
    exported_at: datetime
    user: UserOut
    goals: list[GoalOut]
    constraints: list[ConstraintOut]
