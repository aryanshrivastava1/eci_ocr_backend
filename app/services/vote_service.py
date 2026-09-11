from sqlalchemy import or_, select

from app.models.constituency import Constituency
from app.models.states import State
from app.models.voter import Voter
from app.utils.exceptions import AppException


def get_base_query(db, current_user):
    query = db.query(Voter)

    role = current_user.role

    if role == "booth":
        query = query.filter(Voter.user_id == current_user.id)

    elif role == "constituency":
        query = query.filter(
            Voter.assembly_constituency_id == current_user.constituency_id
        )

    elif role == "district":
        query = query.filter(
            Voter.district_id == current_user.district_id
        )

    elif role == "mandal":
        query = query.filter(
            Voter.mandal_id == current_user.mandal_id
        )

    elif role == "superadmin":
        pass

    else:
        raise AppException(
            status_code=403,
            code="INVALID_ROLE",
            message="Invalid role"
        )

    return query

def apply_voter_filters(
    query,
    name=None,
    epic=None,
    mobile=None,
    state=None,
    district_id=None,
    mandal_id=None,
    assembly_constituency_id=None,
    booth_id=None,
    part_number=None,
    search=None,
    state_id=None,
    state_code=None,
    ac_number=None,
):
    """
    Apply user-supplied filters on top of an already role-scoped query.

    This never widens scope: it is always chained after get_base_query(),
    so a filter can only narrow what the caller is already allowed to see.
    """
    if name:
        query = query.filter(Voter.name.ilike(f"%{name.strip()}%"))

    if epic:
        query = query.filter(Voter.epic.ilike(f"%{epic.strip()}%"))

    if mobile:
        query = query.filter(Voter.mobile.ilike(f"%{mobile.strip()}%"))

    # state is free text on voters (no reference table), so match loosely
    if state:
        query = query.filter(Voter.state.ilike(f"%{state.strip()}%"))

    if district_id is not None:
        query = query.filter(Voter.district_id == district_id)

    if mandal_id is not None:
        query = query.filter(Voter.mandal_id == mandal_id)

    # assembly_constituency_id is the LEGACY constituency.id that voters
    # already store — it is deliberately NOT reinterpreted as an ECI
    # ac_number. Existing callers keep their exact behaviour.
    if assembly_constituency_id is not None:
        query = query.filter(
            Voter.assembly_constituency_id == assembly_constituency_id
        )

    # --- hierarchy filters, added in Step 4D -------------------------------
    # voters carries no state_id column, so a State/UT filter is expressed as
    # "the voter's constituency belongs to this State". The subquery is
    # evaluated in the database against ix_constituency_state_id; no row is
    # fetched into Python to be filtered.
    if state_id is not None or state_code is not None:
        scope = select(Constituency.id)
        if state_id is not None:
            scope = scope.where(Constituency.state_id == state_id)
        if state_code is not None:
            scope = scope.join(
                State, State.state_id == Constituency.state_id
            ).where(State.state_code == str(state_code).strip())
        query = query.filter(Voter.assembly_constituency_id.in_(scope))

    # Official ECI AC number, offered SEPARATELY from assembly_constituency_id
    # so the legacy filter keeps working. An AC number is only unique within a
    # State/UT, so combine it with state_id/state_code for an exact match;
    # on its own it matches that AC number in every loaded State/UT, which is
    # the correct AND semantics for an independent filter.
    if ac_number is not None:
        query = query.filter(
            Voter.assembly_constituency_id.in_(
                select(Constituency.id).where(Constituency.ac_number == ac_number)
            )
        )

    if booth_id is not None:
        query = query.filter(Voter.booth_id == booth_id)

    # no separate numeric part column exists — match the combined
    # "number and name" text, so "45" also matches "145"
    if part_number:
        query = query.filter(
            Voter.part_number_and_name.ilike(f"%{part_number.strip()}%")
        )

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Voter.name.ilike(term),
                Voter.epic.ilike(term),
                Voter.mobile.ilike(term),
            )
        )

    return query
