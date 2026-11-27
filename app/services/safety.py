from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import SafetyEvent
from app.safety.crisis import CrisisCheck
from app.safety.response import build_support_response
from app.schemas.safety import SafetyResponse, SupportResourceOut


def record_safety_event(db: Session, *, surface: str, check: CrisisCheck) -> SafetyEvent:
    """Store which rule fired and where. Never who, and never what was written."""
    row = SafetyEvent(surface=surface, category=check.category, rule_ids=list(check.rule_ids))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def safety_stop(db: Session, *, surface: str, check: CrisisCheck) -> SafetyResponse:
    """Log the event anonymously and build the fixed support response."""
    record_safety_event(db, surface=surface, check=check)
    message, resources = build_support_response(get_settings().crisis_region)
    return SafetyResponse(
        category=check.category,
        message=message,
        resources=[SupportResourceOut.model_validate(r) for r in resources],
    )
