from sqlalchemy.orm import Session

from app.db.models import SafetyEvent
from app.safety.crisis import CrisisCheck


def record_safety_event(db: Session, *, surface: str, check: CrisisCheck) -> SafetyEvent:
    """Store which rule fired and where. Never who, and never what was written."""
    row = SafetyEvent(surface=surface, category=check.category, rule_ids=list(check.rule_ids))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
