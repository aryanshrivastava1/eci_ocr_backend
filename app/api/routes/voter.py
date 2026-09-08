# app/api/routes/voter.py

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.constituency_resolver import resolve_constituency
from app.db.session import get_db
from app.models.constituency import Constituency
from app.models.districts import District
from app.models.voter import Voter
from app.schemas.voter import VoterCreate
from app.api.deps import get_current_user
from app.models.user import User
from app.services.csv_service import generate_csv
from app.services.vote_service import get_base_query
from app.utils.success_response import success_response
from app.utils.exceptions import AppException, SaveStage
from app.core.logger import (
    get_logger, log_stage_failure, log_stage_start, log_stage_success
)
from app.schemas.voter_update_request import VoterUpdateRequest
from app.repositories.voter_repo import create_voter, delete_voter, get_total_voters, update_voter

router = APIRouter()

logger = get_logger("voter")

@router.get("/getVoters")
def get_voters(
    epic: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        if epic:
            booth_id = current_user.booth_id

            if not booth_id:
                raise AppException(
                    status_code=403,
                    code="NO_BOOTH_ASSIGNED",
                    message="Your account has no booth assigned"
                )

            query = (
                db.query(Voter)
                .filter(
                    Voter.epic.ilike(f"%{epic.strip()}%"),
                    Voter.booth_id == booth_id
                )
            )

            total = query.count()

            if total == 0:
                from fastapi.responses import Response
                return Response(status_code=204)

            total_pages = math.ceil(total / limit) if limit > 0 else 1
            offset = (page - 1) * limit
            voters = query.offset(offset).limit(limit).all()

            return success_response(
                data={
                    "voters": [
                        {
                            "id": str(v.id),
                            "name": v.name,
                            "epic": v.epic,
                            "mobile": v.mobile,
                            "address": v.address,
                            "serial_number": v.serial_number,
                            "part_number_and_name": v.part_number_and_name,
                            "assembly_constituency_id": v.assembly_constituency_id,
                            "assembly_constituency_name": v.assembly_constituency_name,
                            "district": v.district,
                            "state": v.state,
                            "mandal_id": v.mandal_id,
                            "district_id": v.district_id,
                            "booth_id": v.booth_id,
                            "user_id": str(v.user_id)
                        }
                        for v in voters
                    ],
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "totalPages": total_pages,
                    "isLastPage": page >= total_pages,
                }
            )

        query = get_base_query(db, current_user)

        total = query.count()
        total_pages = math.ceil(total / limit) if limit > 0 else 1

        offset = (page - 1) * limit
        voters = query.offset(offset).limit(limit).all()

        return success_response(
            data={
                "voters": [
                    {
                        "id": str(v.id),
                        "name": v.name,
                        "epic": v.epic,
                        "mobile": v.mobile,
                        "address": v.address,
                        "serial_number": v.serial_number,
                        "part_number_and_name": v.part_number_and_name,
                        "assembly_constituency_id": v.assembly_constituency_id,
                        "assembly_constituency_name": v.assembly_constituency_name,
                        "district": v.district,
                        "state": v.state,
                        "mandal_id": v.mandal_id,
                        "district_id": v.district_id,
                        "booth_id": v.booth_id,
                        "user_id": str(v.user_id)
                    }
                    for v in voters
                ],
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": total_pages,
                "isLastPage": page >= total_pages,
            }
        )

    except AppException:
        raise

    except Exception as e:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message=f"Something went wrong while fetching voters: {str(e)}"
        )

@router.post("/save")
def create_voter_api(
    payload: VoterCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from sqlalchemy import or_, func

    user_id = getattr(current_user, "id", None)

    try:
        log_stage_start(
            logger, SaveStage.REQUEST_VALIDATION, user_id,
            epic=payload.epic,
            assembly_constituency_name=payload.assembly_constituency_name,
        )

        if not payload.assembly_constituency_name:
            log_stage_failure(
                logger, SaveStage.REQUEST_VALIDATION,
                "assembly_constituency_name missing or blank", user_id,
            )
            raise AppException(
                status_code=400,
                code="INVALID_INPUT",
                message="Assembly constituency name is required",
                field="assembly_constituency_name",
                stage=SaveStage.REQUEST_VALIDATION
            )

        log_stage_success(logger, SaveStage.REQUEST_VALIDATION, user_id)

        log_stage_start(
            logger, SaveStage.CONSTITUENCY_RESOLUTION, user_id,
            raw_name=payload.assembly_constituency_name,
        )

        raw_name = payload.assembly_constituency_name.strip()
        name = raw_name.lower()

        constituency = (
            db.query(Constituency)
            .filter(
                or_(
                    func.lower(Constituency.constituency_hindi) == name,
                    func.lower(Constituency.constituency) == name
                )
            )
            .first()
        )

        if not constituency:
            # No exact match. OCR rarely reproduces the canonical spelling
            # character-for-character (line breaks drop the qualifier, मध्य is
            # read as मण्डल), so fall back to the same resolver the OCR
            # pipeline uses. Only a CONFIRMED match is accepted — a mere
            # candidate is reported back with the suggestion so the operator
            # corrects it, rather than silently filing the voter under the
            # wrong constituency.
            logger.info(
                "no exact constituency match for %r - falling back to resolver",
                raw_name,
            )

            match = resolve_constituency(db, raw_name)

            logger.info(
                "resolver returned status=%s matched=%r score=%s note=%r",
                match.status, match.matched, match.score, match.note,
            )

            if match.status == "confirmed" and match.matched:
                constituency = (
                    db.query(Constituency)
                    .filter(Constituency.constituency_hindi == match.matched)
                    .first()
                )

            if not constituency:
                suggestion = (
                    f" Did you mean '{match.matched}'?"
                    if match.matched else ""
                )
                log_stage_failure(
                    logger, SaveStage.CONSTITUENCY_RESOLUTION,
                    "no confirmed constituency match", user_id,
                    raw_name=raw_name, resolver_status=match.status,
                    best_match=match.matched, score=match.score,
                )
                raise AppException(
                    status_code=400,
                    code="INVALID_CONSTITUENCY",
                    message=(
                        f"'{raw_name}' does not match any assembly "
                        f"constituency.{suggestion} "
                        f"Please correct the constituency and try again."
                    ),
                    field="assembly_constituency_name",
                    stage=SaveStage.CONSTITUENCY_RESOLUTION,
                    details={
                        "raw_name": raw_name,
                        "resolver_status": match.status,
                        "best_match": match.matched,
                        "score": match.score,
                        "note": match.note
                    }
                )

        log_stage_success(
            logger, SaveStage.CONSTITUENCY_RESOLUTION, user_id,
            assembly_constituency_id=constituency.id,
            assembly_constituency_name=constituency.constituency_hindi,
        )

        log_stage_start(
            logger, SaveStage.FIELD_VALIDATION, user_id, epic=payload.epic,
        )

        if payload.epic:
            existing = (
                db.query(Voter)
                .filter(
                    Voter.epic == payload.epic,
                    Voter.assembly_constituency_id == constituency.id
                )
                .first()
            )

            if existing:
                log_stage_failure(
                    logger, SaveStage.FIELD_VALIDATION,
                    "duplicate EPIC in constituency", user_id,
                    epic=payload.epic,
                    assembly_constituency_id=constituency.id,
                    existing_voter_id=str(existing.id),
                )
                raise AppException(
                    status_code=400,
                    code="EPIC_ALREADY_EXISTS",
                    message="Voter with this EPIC already exists",
                    field="epic",
                    stage=SaveStage.FIELD_VALIDATION,
                    details={
                        "epic": payload.epic,
                        "assembly_constituency_id": constituency.id
                    }
                )

        district = (
            db.query(District)
            .filter(District.district_id == constituency.district_id)
            .first()
        )

        data = payload.model_dump()

        data.pop("assembly_constituency_name", None)

        data["assembly_constituency_id"] = constituency.id
        data["assembly_constituency_name"] = constituency.constituency_hindi

        data["district_id"] = constituency.district_id
        data["mandal_id"] = district.mandala_id if district else None

        data["booth_id"] = current_user.booth_id
        data["user_id"] = current_user.id

        data["district"] = (
            district.district_name_hi or district.district_name_en
        ) if district else None

        logger.info(
            "district resolved district_id=%s mandal_id=%s district=%r",
            data["district_id"], data["mandal_id"], data["district"],
        )
        log_stage_success(logger, SaveStage.FIELD_VALIDATION, user_id)

        log_stage_start(logger, SaveStage.DATABASE_SAVE, user_id)

        voter = create_voter(db, data)

        if voter is None:
            # create_voter() returns None when a voter with this EPIC already
            # exists in this constituency. Without this guard the next line
            # raises AttributeError and the operator sees an opaque 500.
            log_stage_failure(
                logger, SaveStage.DATABASE_SAVE,
                "repository reported duplicate EPIC", user_id,
                epic=payload.epic,
                assembly_constituency_id=constituency.id,
            )
            raise AppException(
                status_code=400,
                code="EPIC_ALREADY_EXISTS",
                message="Voter with this EPIC already exists",
                field="epic",
                stage=SaveStage.DATABASE_SAVE,
                details={
                    "epic": payload.epic,
                    "assembly_constituency_id": constituency.id
                }
            )

        return success_response(
            data={
                "id": voter.id,
                "message": "Voter saved successfully"
            }
        )

    except AppException:
        raise

    except Exception as e:
        # The traceback (and any SQL text it carries) stays on the backend;
        # the client gets a sanitised message.
        log_stage_failure(
            logger, "unhandled", "unexpected failure during voter save",
            user_id, exc=e,
        )
        try:
            db.rollback()
        except Exception:
            logger.exception("rollback after failed save also failed")
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="Something went wrong while saving the voter. "
                    "Please try again."
        )
    
@router.put("/{voter_id}")
def update_voter_api(
    voter_id: str,
    ac_id: int,
    payload: VoterUpdateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        data = payload.model_dump(exclude_unset=True)
        data.pop("assembly_constituency_name", None)

        voter = update_voter(db, voter_id, ac_id, data)

        if not voter:
            raise AppException(
                status_code=404,
                code="VOTER_NOT_FOUND",
                message="Voter not found",
                field="voter_id"
            )

        return success_response(
            data={
                "id": voter.id,
                "message": "Voter updated successfully"
            }
        )

    except AppException:
        raise

    except Exception:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="Something went wrong while updating voter"
        )

@router.delete("/{voter_id}")
def delete_voter_api(
    voter_id: str,
    ac_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 🔥 validate UUID
    try:
        voter_id = UUID(voter_id)
    except Exception:
        raise AppException(
            status_code=400,
            code="INVALID_ID",
            message="Invalid voter ID"
        )

    deleted = delete_voter(
        db,
        voter_id,
        ac_id
    )

    if not deleted:
        raise AppException(
            status_code=404,
            code="VOTER_NOT_FOUND",
            message="Voter not found"
        )

    return success_response(
        data={
            "id": str(voter_id),
            "message": "Voter deleted successfully"
        }
    )
@router.get("/count")
def get_voter_count(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    total = get_total_voters(db)

    return success_response(
        data={
            "total_voters": total
        }
    )

from fastapi.responses import FileResponse
from typing import Optional
from fastapi import Query

@router.get("/export")
def export_voters(
    name: Optional[str] = Query(None),
    mobile: Optional[str] = Query(None),
    epic: Optional[str] = Query(None),
    assembly_constituency_id: Optional[int] = Query(None),
    district_id: Optional[int] = Query(None),

    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = get_base_query(db, current_user)

    # -----------------------
    # FILTERS (same as GET)
    # -----------------------
    if name:
        query = query.filter(Voter.name.ilike(f"%{name}%"))

    if mobile:
        query = query.filter(Voter.mobile.ilike(f"%{mobile}%"))

    if epic:
        query = query.filter(Voter.epic.ilike(f"%{epic}%"))

    if assembly_constituency_id:
        query = query.filter(
            Voter.assembly_constituency_id == assembly_constituency_id
        )

    if district_id:
        query = query.filter(Voter.district_id == district_id)

    voters = query.all()

    # generate csv
    file_path = generate_csv(voters)

    return FileResponse(
        path=file_path,
        filename="voters_export.csv",
        media_type="text/csv"
    )