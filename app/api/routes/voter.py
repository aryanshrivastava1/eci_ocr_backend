# app/api/routes/voter.py

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.constituency import Constituency
from app.models.districts import District
from app.models.voter import Voter
from app.schemas.voter import VoterCreate
from app.api.deps import get_current_user
from app.models.user import User
from app.services.csv_service import generate_csv
from app.services.vote_service import apply_voter_filters, get_base_query
from app.utils.success_response import success_response
from app.utils.exceptions import AppException
from app.schemas.voter_update_request import VoterUpdateRequest
from app.repositories.voter_repo import create_voter, delete_voter, get_total_voters, update_voter

router = APIRouter()

# Fields a client is allowed to sort by. Anything else is rejected rather
# than silently ignored.
SORTABLE_FIELDS = {
    "name": Voter.name,
    "epic": Voter.epic,
    "serial_number": Voter.serial_number,
    "part_number_and_name": Voter.part_number_and_name,
    "district_id": Voter.district_id,
    "assembly_constituency_id": Voter.assembly_constituency_id,
}


def _collect_filters(**kwargs) -> dict:
    """Drop unset filters so the response can echo only what was applied."""
    return {k: v for k, v in kwargs.items() if v is not None and v != ""}


def _serialize_voter(v: Voter) -> dict:
    return {
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
        "user_id": str(v.user_id),
    }


def _apply_sort(query, sort_by: str, sort_order: str):
    column = SORTABLE_FIELDS.get(sort_by)

    if column is None:
        raise AppException(
            status_code=400,
            code="INVALID_SORT_FIELD",
            message=(
                "Invalid sort field. Allowed: "
                + ", ".join(sorted(SORTABLE_FIELDS))
            ),
            field="sort_by",
        )

    if sort_order.lower() not in ("asc", "desc"):
        raise AppException(
            status_code=400,
            code="INVALID_SORT_ORDER",
            message="Invalid sort order. Allowed: asc, desc",
            field="sort_order",
        )

    column = column.desc() if sort_order.lower() == "desc" else column.asc()

    # Voter.id is appended as a tiebreaker: without a total order the same
    # row can appear on two different pages.
    return query.order_by(column, Voter.id.asc())


@router.get("/getVoters")
def get_voters(
    name: Optional[str] = Query(None),
    epic: Optional[str] = Query(None),
    mobile: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    district_id: Optional[int] = Query(None),
    mandal_id: Optional[int] = Query(None),
    assembly_constituency_id: Optional[int] = Query(None),
    booth_id: Optional[int] = Query(None),
    part_number: Optional[str] = Query(None),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        query = get_base_query(db, current_user)

        query = apply_voter_filters(
            query,
            name=name,
            epic=epic,
            mobile=mobile,
            state=state,
            district_id=district_id,
            mandal_id=mandal_id,
            assembly_constituency_id=assembly_constituency_id,
            booth_id=booth_id,
            part_number=part_number,
            search=search,
        )

        total = query.count()
        total_pages = math.ceil(total / limit) if total else 0

        query = _apply_sort(query, sort_by, sort_order)

        offset = (page - 1) * limit
        voters = query.offset(offset).limit(limit).all()

        return success_response(
            data={
                "voters": [_serialize_voter(v) for v in voters],
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": total_pages,
                "isLastPage": page >= total_pages,
                "appliedFilters": _collect_filters(
                    name=name,
                    epic=epic,
                    mobile=mobile,
                    search=search,
                    state=state,
                    district_id=district_id,
                    mandal_id=mandal_id,
                    assembly_constituency_id=assembly_constituency_id,
                    booth_id=booth_id,
                    part_number=part_number,
                ),
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

    try:
        if not payload.assembly_constituency_name:
            raise AppException(
                status_code=400,
                code="INVALID_INPUT",
                message="Assembly constituency name is required",
                field="assembly_constituency_name"
            )

        name = payload.assembly_constituency_name.strip().lower()

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
            raise AppException(
                status_code=400,
                code="INVALID_CONSTITUENCY",
                message="Invalid assembly constituency",
                field="assembly_constituency_name"
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
                raise AppException(
                    status_code=400,
                    code="EPIC_ALREADY_EXISTS",
                    message="Voter with this EPIC already exists",
                    field="epic"
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

        voter = create_voter(db, data)

        return success_response(
            data={
                "id": voter.id,
                "message": "Voter saved successfully"
            }
        )

    except AppException:
        raise

    except Exception as e:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message=str(e)
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
    name: Optional[str] = Query(None),
    epic: Optional[str] = Query(None),
    mobile: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    district_id: Optional[int] = Query(None),
    mandal_id: Optional[int] = Query(None),
    assembly_constituency_id: Optional[int] = Query(None),
    booth_id: Optional[int] = Query(None),
    part_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        query = get_base_query(db, current_user)

        query = apply_voter_filters(
            query,
            name=name,
            epic=epic,
            mobile=mobile,
            state=state,
            district_id=district_id,
            mandal_id=mandal_id,
            assembly_constituency_id=assembly_constituency_id,
            booth_id=booth_id,
            part_number=part_number,
            search=search,
        )

        return success_response(
            data={
                "total_voters": query.count(),
                "appliedFilters": _collect_filters(
                    name=name,
                    epic=epic,
                    mobile=mobile,
                    search=search,
                    state=state,
                    district_id=district_id,
                    mandal_id=mandal_id,
                    assembly_constituency_id=assembly_constituency_id,
                    booth_id=booth_id,
                    part_number=part_number,
                ),
            }
        )

    except AppException:
        raise

    except Exception as e:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message=f"Something went wrong while counting voters: {str(e)}"
        )


@router.get("/export")
def export_voters(
    name: Optional[str] = Query(None),
    epic: Optional[str] = Query(None),
    mobile: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    district_id: Optional[int] = Query(None),
    mandal_id: Optional[int] = Query(None),
    assembly_constituency_id: Optional[int] = Query(None),
    booth_id: Optional[int] = Query(None),
    part_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = get_base_query(db, current_user)

    query = apply_voter_filters(
        query,
        name=name,
        epic=epic,
        mobile=mobile,
        state=state,
        district_id=district_id,
        mandal_id=mandal_id,
        assembly_constituency_id=assembly_constituency_id,
        booth_id=booth_id,
        part_number=part_number,
        search=search,
    )

    voters = query.all()

    file_path = generate_csv(voters)

    return FileResponse(
        path=file_path,
        filename="voters_export.csv",
        media_type="text/csv"
    )
