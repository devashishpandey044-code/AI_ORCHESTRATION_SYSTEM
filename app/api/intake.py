"""Routes for the life intake and the obstacle list.

No model is called here: the intake stores what the user typed, and the extraction that
reads it comes later. The crisis check runs before anything is written, and when it
fires nothing is stored at all. Keeping the text would put a crisis disclosure in the
database, which SafetyEvent deliberately avoids doing.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.deps import CurrentUser, DbSession
from app.db.intake_models import Obstacle
from app.intake import questions
from app.intake.questions import QuestionKind
from app.intake.types import ObstacleStatus
from app.safety.crisis import check_text
from app.schemas.intake import (
    IntakeAnswerIn,
    IntakeAnswerOut,
    IntakeProgress,
    ObstacleCreate,
    ObstacleOut,
    ObstacleUpdate,
    QuestionOut,
)
from app.schemas.safety import SafetyResponse
from app.services import intake as service
from app.services.safety import safety_stop

router = APIRouter(prefix="/intake", tags=["intake"])
obstacles_router = APIRouter(prefix="/obstacles", tags=["obstacles"])


class AnswerValue(BaseModel):
    """The body of a saved answer. Which question it answers comes from the path."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    value: str = Field(min_length=1, max_length=2000)


class AnswerSaved(BaseModel):
    """Either the saved answer, or the support response if the safety check fired."""

    answer: IntakeAnswerOut | None = None
    safety: SafetyResponse | None = None


class ObstacleSaved(BaseModel):
    """Either the recorded problem, or the support response if the safety check fired."""

    obstacle: ObstacleOut | None = None
    safety: SafetyResponse | None = None


def _first_message(error: ValidationError) -> str:
    message = str(error.errors()[0].get("msg", "invalid answer"))
    # Pydantic prefixes what a validator raised; the person does not need to see that.
    return message.removeprefix("Value error, ")


def _owned(db: DbSession, user_id: uuid.UUID, obstacle_id: uuid.UUID) -> Obstacle:
    obstacle = service.get_obstacle(db, user_id, obstacle_id)
    if obstacle is None:
        raise HTTPException(404, "Problem not found")
    return obstacle


@router.get("/questions", response_model=list[QuestionOut])
def list_questions() -> list[QuestionOut]:
    """The question catalogue.

    Unauthenticated on purpose: it is fixed content with no user data in it, and the
    page needs it to show what the intake will ask before anyone signs up.
    """
    return [QuestionOut.model_validate(q) for q in questions.QUESTIONS]


@router.get("/answers", response_model=list[IntakeAnswerOut])
def list_answers(user: CurrentUser, db: DbSession) -> list[IntakeAnswerOut]:
    rows = service.list_answers(db, user.id)
    return [IntakeAnswerOut.model_validate(row) for row in rows]


@router.get("/progress", response_model=IntakeProgress)
def intake_progress(user: CurrentUser, db: DbSession) -> IntakeProgress:
    return service.progress(db, user.id)


@router.put("/answers/{question_key}", response_model=AnswerSaved)
def save_answer(
    question_key: str, payload: AnswerValue, user: CurrentUser, db: DbSession
) -> AnswerSaved:
    """Save or replace one answer.

    The value is validated against its own catalogue question, so a time question
    cannot take prose and a number cannot fall outside its bounds.
    """
    try:
        answer = IntakeAnswerIn(question_key=question_key, value=payload.value)
    except ValidationError as error:
        raise HTTPException(422, _first_message(error)) from None

    question = questions.get(answer.question_key)
    # Only free text can carry a disclosure; a time or a number cannot.
    if question is not None and question.kind is QuestionKind.TEXT:
        check = check_text(answer.value)
        if check.triggered:
            return AnswerSaved(safety=safety_stop(db, surface="intake", check=check))

    row = service.upsert_answer(db, user.id, answer.question_key, answer.value)
    return AnswerSaved(answer=IntakeAnswerOut.model_validate(row))


@obstacles_router.post("", response_model=ObstacleSaved, status_code=201)
def add_obstacle(
    payload: ObstacleCreate, user: CurrentUser, db: DbSession, response: Response
) -> ObstacleSaved:
    """Record a problem the user says is holding them back.

    Returns 201 when a problem is stored, and 200 with the support response when the
    safety check fires, because in that case nothing was created.
    """
    check = check_text(payload.text)
    if check.triggered:
        response.status_code = 200
        return ObstacleSaved(safety=safety_stop(db, surface="obstacles", check=check))
    try:
        row = service.create_obstacle(db, user.id, payload.text, payload.severity)
    except service.IntakeError as error:
        raise HTTPException(409, str(error)) from None
    return ObstacleSaved(obstacle=ObstacleOut.model_validate(row))


@obstacles_router.get("", response_model=list[ObstacleOut])
def list_obstacles(
    user: CurrentUser, db: DbSession, status: ObstacleStatus | None = None
) -> list[ObstacleOut]:
    rows = service.list_obstacles(db, user.id, status)
    return [ObstacleOut.model_validate(row) for row in rows]


@obstacles_router.patch("/{obstacle_id}", response_model=ObstacleOut)
def update_obstacle(
    obstacle_id: uuid.UUID, payload: ObstacleUpdate, user: CurrentUser, db: DbSession
) -> Obstacle:
    obstacle = _owned(db, user.id, obstacle_id)
    try:
        return service.update_obstacle(
            db, obstacle, status=payload.status, severity=payload.severity
        )
    except service.IntakeError as error:
        raise HTTPException(409, str(error)) from None


@obstacles_router.delete("/{obstacle_id}", status_code=204)
def delete_obstacle(obstacle_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    service.delete_obstacle(db, _owned(db, user.id, obstacle_id))
    return Response(status_code=204)
