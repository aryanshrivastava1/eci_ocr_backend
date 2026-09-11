# app/api/routes/geo.py
"""Hierarchical geography APIs: State/UT -> District -> Assembly Constituency.

The reference data is India-wide: 36 States/UTs, 784 districts and 3,551
Assembly Constituencies. Cascading, parent-scoped endpoints are the intended
way to drive the Flutter pickers:

    GET /geo/states
    GET /geo/districts?state_id=9
    GET /geo/constituencies?district_id=127

Authoritative identifiers are the LGD codes (`state_code`,
`lgd_district_code`, both TEXT) and `(state_id, ac_number)` for an AC.
`constituency.id` stays the database primary key that
`voters.assembly_constituency_id` references — it is NOT the AC number and
must never be shown as one. Every response carries both, separately.

All filtering is done in the database. No endpoint here loads a table into
Python to filter it, and none does fuzzy matching.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.constituency import Constituency
from app.models.districts import District
from app.models.states import State
from app.utils.exceptions import AppException
from app.utils.success_response import success_response

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models — these exist so the generated OpenAPI schema documents the
# shape of `data`. The envelope itself stays {success, message, data}.
# ---------------------------------------------------------------------------

class StateOut(BaseModel):
    state_id: int = Field(..., description="Primary key; equals the LGD State Code as an integer")
    state_code: str = Field(..., description='Authoritative LGD State Code as TEXT, e.g. "9" for Uttar Pradesh')
    state_name_en: str
    state_name_hi: Optional[str] = Field(
        None,
        description="NULL until an authoritative Hindi source is loaded. Never fabricated.",
    )


class DistrictOut(BaseModel):
    district_id: int = Field(..., description="Legacy database primary key; voters.district_id references this")
    lgd_district_code: Optional[str] = Field(..., description="Authoritative LGD District Code as TEXT, globally unique")
    district_name_en: Optional[str]
    district_name_hi: Optional[str] = Field(None, description="Populated for the 75 Uttar Pradesh districts only")
    state_id: Optional[int]
    state_code: Optional[str] = None
    state_name_en: Optional[str] = None
    mandal_id: Optional[int] = Field(None, description="Legacy column (districts.mandala_id); NULL everywhere")


class ConstituencyOut(BaseModel):
    id: int = Field(..., description="Database primary key. NOT the AC number — do not display it as one")
    ac_number: Optional[int] = Field(..., description="Official ECI Assembly Constituency number; display this")
    constituency: str
    constituency_hindi: Optional[str] = Field(
        None, description="Populated for the 9 Lucknow rows only; the ECI source has no Devanagari"
    )
    reservation: Optional[str] = Field(
        None,
        description=(
            "SC / ST / null. Not yet stored in the database — see "
            "docs/step-4d-geo-api-report.md. Always null for now."
        ),
    )
    state_id: Optional[int]
    state_code: Optional[str] = None
    district_id: Optional[int] = Field(
        None, description="NULL for 104 rows (Delhi, and headings with no unambiguous LGD successor)"
    )
    lgd_district_code: Optional[str] = None
    district: Optional[str] = Field(None, description="Legacy free-text district name column")
    district_name_en: Optional[str] = None


class StatesData(BaseModel):
    states: List[StateOut]
    total: int


class DistrictsData(BaseModel):
    districts: List[DistrictOut]
    total: int


class ConstituenciesData(BaseModel):
    constituencies: List[ConstituencyOut]
    total: int


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _serialize_state(s: State) -> dict:
    return {
        "state_id": s.state_id,
        "state_code": s.state_code,
        "state_name_en": s.state_name_en,
        # NULL for all 36 rows today. LGD's "local language" column is a Latin
        # transliteration, not Devanagari, so it is not used here.
        "state_name_hi": s.state_name_hi,
    }


def _serialize_district(row) -> dict:
    """row is (District, state_code, state_name_en) or a bare District."""
    d, state_code, state_name_en = row if isinstance(row, tuple) else (row, None, None)
    return {
        "district_id": d.district_id,
        "lgd_district_code": d.lgd_district_code,
        "district_name_en": d.district_name_en,
        "district_name_hi": d.district_name_hi,
        "state_id": d.state_id,
        "state_code": state_code,
        "state_name_en": state_name_en,
        # column is spelled mandala_id in the table; normalised here to
        # match Voter.mandal_id. No mandal name table exists.
        "mandal_id": d.mandala_id,
    }


def _serialize_constituency(row) -> dict:
    """row is (Constituency, state_code, district_name_en) or a bare Constituency."""
    c, state_code, district_name_en = (
        row if isinstance(row, tuple) else (row, None, None)
    )
    return {
        # Database primary key. Kept because voters.assembly_constituency_id
        # references it. It is NOT the AC number.
        "id": c.id,
        # The number a user should see: "AC 168", not "ID 13".
        "ac_number": c.ac_number,
        "constituency": c.constituency,
        "constituency_hindi": c.constituency_hindi,
        # No reservation column exists in the database yet; see the report.
        "reservation": None,
        "state_id": c.state_id,
        "state_code": state_code,
        "district_id": c.district_id,
        "lgd_district_code": c.lgd_district_code,
        "district": c.district,
        "district_name_en": district_name_en,
    }


# ---------------------------------------------------------------------------
# Parent validation — the project convention is AppException
# ---------------------------------------------------------------------------

def _require_state(db: Session, state_id: Optional[int]) -> Optional[State]:
    if state_id is None:
        return None
    state = db.get(State, state_id)
    if state is None:
        raise AppException(
            status_code=404,
            code="STATE_NOT_FOUND",
            message=f"No State/UT with state_id {state_id}",
            field="state_id",
        )
    return state


def _require_district(db: Session, district_id: Optional[int]) -> Optional[District]:
    if district_id is None:
        return None
    district = db.get(District, district_id)
    if district is None:
        raise AppException(
            status_code=404,
            code="DISTRICT_NOT_FOUND",
            message=f"No district with district_id {district_id}",
            field="district_id",
        )
    return district


# ---------------------------------------------------------------------------
# Queries — filtering happens in the database
# ---------------------------------------------------------------------------

def _states_query(db: Session, search: Optional[str] = None):
    stmt = select(State)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                State.state_name_en.ilike(term),
                State.state_name_hi.ilike(term),
                State.state_code == search.strip(),
            )
        )
    # deterministic: name, then the stable primary key as a tiebreaker
    return stmt.order_by(State.state_name_en, State.state_id)


def _districts_query(
    db: Session,
    state_id: Optional[int] = None,
    search: Optional[str] = None,
):
    stmt = (
        select(District, State.state_code, State.state_name_en)
        .outerjoin(State, State.state_id == District.state_id)
    )
    # Parent scope first, so a search can never escape the selected State.
    if state_id is not None:
        stmt = stmt.where(District.state_id == state_id)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                District.district_name_en.ilike(term),
                District.district_name_hi.ilike(term),
                District.lgd_district_code == search.strip(),
            )
        )
    return stmt.order_by(District.district_name_en, District.district_id)


def _constituencies_query(
    db: Session,
    state_id: Optional[int] = None,
    district_id: Optional[int] = None,
    ac_number: Optional[int] = None,
    search: Optional[str] = None,
):
    stmt = (
        select(Constituency, State.state_code, District.district_name_en)
        .outerjoin(State, State.state_id == Constituency.state_id)
        .outerjoin(District, District.district_id == Constituency.district_id)
    )
    # Parent scope first — a search is always narrowed to it.
    if district_id is not None:
        stmt = stmt.where(Constituency.district_id == district_id)
    if state_id is not None:
        stmt = stmt.where(Constituency.state_id == state_id)
    if ac_number is not None:
        stmt = stmt.where(Constituency.ac_number == ac_number)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Constituency.constituency.ilike(term),
                Constituency.constituency_hindi.ilike(term),
            )
        )
    # Ascending AC number is the order a user expects: AC 168, 169, 170...
    return stmt.order_by(Constituency.ac_number, Constituency.id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/states",
    summary="List all States/UTs",
    response_description="All 36 LGD States/UTs, ordered by English name",
)
def list_states(
    search: Optional[str] = Query(
        None, description="Case-insensitive match on the English or Hindi name, or an exact state_code"
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Top of the hierarchy. Use the returned `state_id` for `/geo/districts`."""
    try:
        rows = db.execute(_states_query(db, search)).scalars().all()
        return success_response(
            data={
                "states": [_serialize_state(s) for s in rows],
                "total": len(rows),
            }
        )
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message=f"Something went wrong while fetching states: {str(e)}",
        )


@router.get(
    "/districts",
    summary="List districts, optionally scoped to one State/UT",
    response_description="Districts ordered by English name",
)
def list_districts(
    state_id: Optional[int] = Query(
        None, description="Restrict to one State/UT. Strongly recommended — without it all 784 districts are returned."
    ),
    search: Optional[str] = Query(
        None, description="Case-insensitive match on the English or Hindi district name, or an exact lgd_district_code. Always scoped to state_id when it is supplied."
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Second level of the hierarchy.

    `state_id` is optional only for backward compatibility with clients written
    against the pre-India-wide API. New clients should always pass it.
    """
    try:
        _require_state(db, state_id)
        rows = db.execute(_districts_query(db, state_id, search)).all()
        return success_response(
            data={
                "districts": [_serialize_district(tuple(r)) for r in rows],
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


@router.get(
    "/constituencies",
    summary="List Assembly Constituencies, scoped to a district or State/UT",
    response_description="Constituencies ordered by ac_number ascending",
)
def list_constituencies(
    district_id: Optional[int] = Query(
        None, description="Restrict to one district. This is the normal cascading call."
    ),
    state_id: Optional[int] = Query(
        None, description="Restrict to one State/UT. Combine with district_id to enforce both."
    ),
    ac_number: Optional[int] = Query(
        None, description="Filter by the official ECI AC number (not the database id)."
    ),
    search: Optional[str] = Query(
        None, description="Case-insensitive match on the English or Hindi AC name. Always scoped to the parent filters."
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Third level of the hierarchy.

    Display `ac_number` to users, never `id`. `id` is the database primary key
    that `voters.assembly_constituency_id` references.
    """
    try:
        _require_state(db, state_id)
        _require_district(db, district_id)
        rows = db.execute(
            _constituencies_query(db, state_id, district_id, ac_number, search)
        ).all()
        return success_response(
            data={
                "constituencies": [_serialize_constituency(tuple(r)) for r in rows],
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


@router.get(
    "/filters",
    summary="DEPRECATED bulk filter payload — prefer the cascading endpoints",
    response_description="States, districts and constituencies in one response",
    deprecated=True,
)
def get_filter_options(
    state_id: Optional[int] = Query(
        None, description="Scope the districts and constituencies to one State/UT."
    ),
    district_id: Optional[int] = Query(
        None, description="Scope the constituencies to one district."
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Districts + constituencies in one call, to populate a filter panel.

    DEPRECATED. Kept working unchanged for existing Flutter builds, which may
    call it with no parameters. Unscoped it now returns 784 districts and
    3,551 constituencies in a single response — new clients should use
    `/geo/states` -> `/geo/districts?state_id=` -> `/geo/constituencies?district_id=`
    instead, or pass `state_id`/`district_id` here to scope the payload.

    `states` was added to the payload; the pre-existing `districts` and
    `constituencies` keys are unchanged in shape and position.
    """
    try:
        _require_state(db, state_id)
        _require_district(db, district_id)

        states = db.execute(_states_query(db)).scalars().all()
        districts = db.execute(_districts_query(db, state_id)).all()
        constituencies = db.execute(
            _constituencies_query(db, state_id, district_id)
        ).all()

        return success_response(
            data={
                "states": [_serialize_state(s) for s in states],
                "districts": [_serialize_district(tuple(r)) for r in districts],
                "constituencies": [
                    _serialize_constituency(tuple(r)) for r in constituencies
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
