import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import LifeModelSource, LifeModelVersion
from app.schemas.life_model import LifeModelData


def get_current(db: Session, user_id: uuid.UUID) -> LifeModelVersion | None:
    stmt = (
        select(LifeModelVersion)
        .where(LifeModelVersion.user_id == user_id)
        .order_by(LifeModelVersion.version.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def get_version(db: Session, user_id: uuid.UUID, version: int) -> LifeModelVersion | None:
    stmt = select(LifeModelVersion).where(
        LifeModelVersion.user_id == user_id, LifeModelVersion.version == version
    )
    return db.scalar(stmt)


def list_versions(db: Session, user_id: uuid.UUID) -> list[LifeModelVersion]:
    stmt = (
        select(LifeModelVersion)
        .where(LifeModelVersion.user_id == user_id)
        .order_by(LifeModelVersion.version.desc())
    )
    return list(db.scalars(stmt))


def save_new_version(
    db: Session, user_id: uuid.UUID, data: LifeModelData, source: LifeModelSource
) -> LifeModelVersion:
    """Append a new immutable version. Old versions are never edited."""
    latest = db.scalar(
        select(func.max(LifeModelVersion.version)).where(LifeModelVersion.user_id == user_id)
    )
    row = LifeModelVersion(
        user_id=user_id,
        version=(latest or 0) + 1,
        source=source,
        data=data.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def parse_data(row: LifeModelVersion) -> LifeModelData:
    return LifeModelData.model_validate(row.data)
