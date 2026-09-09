# app/api/routes/geo.py

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.constituency import Constituency
from app.models.districts import District
from app.utils.exceptions import AppException
from app.utils.success_response import success_response

router = APIRouter()


def _serialize_district(d: District) -> dict:
    return {
        "district_id": d.district_id,
        "district_name_en": d.district_name_en,
        "district_name_hi": d.district_name_hi,
        # column is spelled mandala_id in the table; normalised here to
        # match Voter.mandal_id. No mandal name table exists.
        "mandal_id": d.mandala_id,
    }


def _serialize_constituency(c: Constituency) -> dict:
    return {
        "id": c.id,
        "constituency": c.constituency,
        "constituency_hindi": c.constituency_hindi,
        "district": c.district,
        "district_id": c.district_id,
    }


def _districts_query(db: Session, search: Optional[str] = None):
    query = db.query(District)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                District.district_name_en.ilike(term),
                District.district_name_hi.ilike(term),
            )
        )

    return query.order_by(District.district_name_en, District.district_id)


def _constituencies_query(
    db: Session,
    district_id: Optional[int] = None,
    search: Optional[str] = None,
):
    query = db.query(Constituency)

    if district_id is not None:
        query = query.filter(Constituency.district_id == district_id)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Constituency.constituency.ilike(term),
                Constituency.constituency_hindi.ilike(term),
            )
        )

    return query.order_by(Constituency.constituency, Constituency.id)


@router.get("/districts")
def list_districts(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        rows = _districts_query(db, search).all()

        return success_response(
            data={
                "districts": [_serialize_district(d) for d in rows],
                "total": len(rows),
            }
        )

    except AppException:
        raise

    except Exception as e:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message=f"Something went wrong while fetching districts: {str(e)}",
        )


@router.get("/constituencies")
def list_constituencies(
    district_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        rows = _constituencies_query(db, district_id, search).all()

        return success_response(
            data={
                "constituencies": [_serialize_constituency(c) for c in rows],
                "total": len(rows),
            }
        )

    except AppException:
        raise

    except Exception as e:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message=(
                f"Something went wrong while fetching constituencies: {str(e)}"
            ),
        )


@router.get("/filters")
def get_filter_options(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Districts + constituencies in one call, to populate a filter panel."""
    try:
        districts = _districts_query(db).all()
        constituencies = _constituencies_query(db).all()

        return success_response(
            data={
                "districts": [_serialize_district(d) for d in districts],
                "constituencies": [
                    _serialize_constituency(c) for c in constituencies
                ],
            }
        )

    except AppException:
        raise

    except Exception as e:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message=(
                f"Something went wrong while fetching filter options: {str(e)}"
            ),
        )
