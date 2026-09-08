from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logger import get_logger, log_stage_failure, log_stage_success
from app.models.voter import Voter
from app.utils.exceptions import AppException, SaveStage

logger = get_logger("voter_repo")


def create_voter(db: Session, data: dict):
    existing = db.query(Voter).filter(
        Voter.epic == data.get("epic"),
        Voter.assembly_constituency_id == data.get("assembly_constituency_id")
    ).first()

    if existing:
        return None

    voter = Voter(**data)

    # Stage 4 — database_save. Flushing separately from the commit tells the
    # two apart: a constraint or partition-routing violation surfaces here,
    # a transaction-level failure surfaces in the commit below. Either way the
    # session is rolled back, so the pooled connection is not handed back to
    # the next request in a dirty state.
    try:
        db.add(voter)
        db.flush()
    except SQLAlchemyError as e:
        db.rollback()
        log_stage_failure(
            logger, SaveStage.DATABASE_SAVE, "flush failed",
            epic=data.get("epic"),
            assembly_constituency_id=data.get("assembly_constituency_id"),
            exc=e,
        )
        raise AppException(
            status_code=500,
            code="DATABASE_SAVE_FAILED",
            message="Could not save the voter record. Please try again.",
            stage=SaveStage.DATABASE_SAVE
        )

    # Stage 5 — commit.
    try:
        db.commit()
        db.refresh(voter)
    except SQLAlchemyError as e:
        db.rollback()
        log_stage_failure(
            logger, SaveStage.COMMIT, "commit failed",
            epic=data.get("epic"),
            assembly_constituency_id=data.get("assembly_constituency_id"),
            exc=e,
        )
        raise AppException(
            status_code=500,
            code="DATABASE_COMMIT_FAILED",
            message="Could not save the voter record. Please try again.",
            stage=SaveStage.COMMIT
        )

    log_stage_success(logger, SaveStage.COMMIT, voter_id=str(voter.id))

    return voter

def update_voter(db: Session, voter_id: str, ac_id: int, data: dict):
    voter = (
        db.query(Voter)
        .filter(
            Voter.id == voter_id,
            Voter.assembly_constituency_id == ac_id  # 🔥 partition targeting
        )
        .first()
    )

    if not voter:
        return None

    for key, value in data.items():
        if value is not None:
            setattr(voter, key, value)

    try:
        db.commit()
        db.refresh(voter)
    except SQLAlchemyError as e:
        db.rollback()
        log_stage_failure(
            logger, SaveStage.COMMIT, "commit failed on update",
            voter_id=str(voter_id), assembly_constituency_id=ac_id, exc=e,
        )
        raise AppException(
            status_code=500,
            code="DATABASE_COMMIT_FAILED",
            message="Could not update the voter record. Please try again.",
            stage=SaveStage.COMMIT
        )

    return voter

def delete_voter(db: Session, voter_id: UUID, ac_id: int):
    voter = (
        db.query(Voter)
        .filter(
            Voter.id == voter_id,
            Voter.assembly_constituency_id == ac_id
        )
        .first()
    )

    if not voter:
        return False

    try:
        db.delete(voter)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        log_stage_failure(
            logger, SaveStage.COMMIT, "commit failed on delete",
            voter_id=str(voter_id), assembly_constituency_id=ac_id, exc=e,
        )
        raise AppException(
            status_code=500,
            code="DATABASE_COMMIT_FAILED",
            message="Could not delete the voter record. Please try again.",
            stage=SaveStage.COMMIT
        )

    return True

def get_total_voters(db: Session):
    return db.query(Voter).count()