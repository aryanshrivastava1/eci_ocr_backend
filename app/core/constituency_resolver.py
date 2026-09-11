"""Resolve a raw constituency string to a canonical DB constituency row.

The database now holds 3,551 Assembly Constituencies across 25 States/UTs, and
83 English AC names are duplicated across states (185 rows). Resolution is
therefore SCOPED: a candidate set is narrowed in PostgreSQL by state and
district first, and fuzzy matching only ever runs inside that narrowed set.

Resolution hierarchy
    1. state   — from an explicit LGD state_code, else the state name
    2. district— from an explicit LGD district code, else the district name
                 (a district name resolves the state too, when the state was
                 not supplied)
    3. exact constituency name match inside the scope
    4. fuzzy match, inside the scope only

An unscoped request is answered only when it is provably safe: an exact name
match that is globally unique, or a fuzzy match whose plausible candidates all
belong to a single state. Anything else returns an explicit unresolved result
listing the candidates. `.first()` is never used to break a tie.

Authoritative identifiers: `states.state_code` (LGD State Code, TEXT),
`districts.lgd_district_code` (LGD District Code, TEXT), and
`(state_id, ac_number)` for an AC. `constituency.id` remains the database
primary key that `voters.assembly_constituency_id` references; this module
never writes to any table.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz, process
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.constituency import Constituency
from app.models.districts import District
from app.models.states import State

# Fuzzy match threshold — strings must be at least this similar (0–100).
# Unchanged from the pre-India-wide behaviour: scoping, not a looser
# threshold, is what makes resolution work at national scale.
_MATCH_THRESHOLD = 65

# Hard cap on how many rows an unscoped lookup may pull into Python. An
# unscoped query that is broader than this is refused as unsafe rather than
# answered on a guess.
_UNSCOPED_CANDIDATE_CAP = 200

# Status values returned in Resolution.status
RESOLVED = "resolved"
UNRESOLVED_NOT_FOUND = "unresolved_not_found"
UNRESOLVED_AMBIGUOUS = "unresolved_ambiguous"
UNRESOLVED_SCOPE_REQUIRED = "unresolved_scope_required"
UNRESOLVED_SCOPE_CONFLICT = "unresolved_scope_conflict"

# Devanagari label prefixes the OCR text often carries, e.g.
# "जिला : लखनऊ" or "विधान सभा निर्वाचन क्षेत्र". Stripped for comparison only;
# the stored values are never rewritten and nothing is transliterated.
_DISTRICT_PREFIX = re.compile(r"^\s*(?:ज़?िल[ाेोां]*|district)\s*[:：\-]?\s*", re.I)
_AC_PREFIX = re.compile(
    r"^\s*(?:विधान\s*सभा(?:\s*निर्वाचन)?(?:\s*क्षेत्र)?|assembly\s*constituency)"
    r"\s*[:：\-]?\s*",
    re.I,
)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _norm(value: Optional[str]) -> str:
    """Unicode-safe normalisation for comparison only.

    NFC-normalises (so decomposed Devanagari matras compare equal to composed
    ones), collapses whitespace and case-folds. Devanagari is preserved intact:
    nothing is stripped from the script and nothing is transliterated.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _is_devanagari(value: Optional[str]) -> bool:
    return bool(value) and bool(_DEVANAGARI.search(value))


def _strip_prefix(value: Optional[str], pattern: re.Pattern) -> str:
    if not value:
        return ""
    return pattern.sub("", unicodedata.normalize("NFC", str(value))).strip()


@dataclass
class Candidate:
    """A constituency row, flattened for the caller and for tie inspection."""

    constituency_id: int
    state_id: int
    state_code: str
    state_name_en: str
    ac_number: int
    constituency: str
    constituency_hindi: Optional[str]
    district_id: Optional[int]
    district_name_en: Optional[str]
    district_name_hi: Optional[str]
    lgd_district_code: Optional[str]

    def brief(self) -> dict:
        """Small dict safe to return in an API error payload."""
        return {
            "constituency_id": self.constituency_id,
            "state_code": self.state_code,
            "state_name_en": self.state_name_en,
            "ac_number": self.ac_number,
            "constituency": self.constituency,
            "constituency_hindi": self.constituency_hindi,
            "district_lgd_code": self.lgd_district_code,
            "district_name_en": self.district_name_en,
        }


@dataclass
class Scope:
    state_id: Optional[int] = None
    state_code: Optional[str] = None
    state_name_en: Optional[str] = None
    district_id: Optional[int] = None
    lgd_district_code: Optional[str] = None
    district_name_en: Optional[str] = None
    # why the scope ended up as it did, for logs and API messages
    notes: list[str] = field(default_factory=list)
    conflict: Optional[str] = None

    @property
    def level(self) -> str:
        if self.district_id is not None:
            return "district"
        if self.state_id is not None:
            return "state"
        return "global"


@dataclass
class Resolution:
    status: str
    scope: Scope
    match: Optional[Candidate] = None
    candidates: list[Candidate] = field(default_factory=list)
    method: Optional[str] = None          # exact | fuzzy
    score: Optional[float] = None
    reason: Optional[str] = None
    # Which identity the caller should supply to make an ambiguous case
    # resolvable. Never a guess at what the value should be.
    required: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "scope": self.scope.level,
            "state_code": self.scope.state_code,
            "district_lgd_code": self.scope.lgd_district_code,
            "method": self.method,
            "score": self.score,
            "reason": self.reason,
            "required": self.required,
            "match": self.match.brief() if self.match else None,
            "candidates": [c.brief() for c in self.candidates],
        }


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------

def resolve_state(
    db: Session,
    state_code: Optional[str] = None,
    state_name: Optional[str] = None,
) -> tuple[Optional[State], Optional[str]]:
    """Resolve a State/UT. Returns (State | None, note).

    An explicit LGD state_code wins. Otherwise the name is matched against
    states.state_name_en and states.state_name_hi.

    Note on Hindi: states.state_name_hi is currently NULL for all 36 rows
    because no authoritative Hindi source has been established (see
    docs/eci-ac-research.md). A Devanagari state name therefore cannot resolve
    a state today, and no Hindi state names are invented here to make it look
    as though it can. The branch is in place so that resolution starts working
    the moment authoritative Hindi is loaded. Until then a Devanagari state
    string is ignored for scoping and the district name carries the state.
    """
    if state_code is not None and str(state_code).strip():
        code = str(state_code).strip()
        row = db.execute(
            select(State).where(State.state_code == code)
        ).scalars().first()
        if row:
            return row, "state from explicit LGD state_code"
        return None, "state_code %r does not exist in states" % code

    if state_name and str(state_name).strip():
        target = _norm(state_name)
        row = db.execute(
            select(State).where(
                or_(
                    func.lower(func.trim(State.state_name_en)) == target,
                    func.lower(func.trim(State.state_name_hi)) == target,
                )
            )
        ).scalars().first()
        if row:
            return row, "state from name"
        if _is_devanagari(state_name):
            return None, (
                "state name is Devanagari and states.state_name_hi is not "
                "populated, so it cannot scope the lookup"
            )
        return None, "state name %r did not match any State/UT" % state_name

    return None, None


def resolve_district(
    db: Session,
    lgd_district_code: Optional[str] = None,
    district_name: Optional[str] = None,
    state_id: Optional[int] = None,
) -> tuple[Optional[District], Optional[str]]:
    """Resolve a district. Returns (District | None, note).

    An explicit LGD District Code wins — it is globally unique. Otherwise the
    name is matched against district_name_en and district_name_hi, restricted
    to the state when one is known. District names are NOT unique across
    states, so a name that matches in more than one state without a state
    scope is reported ambiguous rather than guessed.
    """
    if lgd_district_code is not None and str(lgd_district_code).strip():
        code = str(lgd_district_code).strip()
        row = db.execute(
            select(District).where(District.lgd_district_code == code)
        ).scalars().first()
        if row:
            return row, "district from explicit LGD district code"
        return None, "lgd_district_code %r does not exist in districts" % code

    cleaned = _strip_prefix(district_name, _DISTRICT_PREFIX)
    if not cleaned:
        return None, None

    target = _norm(cleaned)
    stmt = select(District).where(
        or_(
            func.lower(func.trim(District.district_name_en)) == target,
            func.lower(func.trim(District.district_name_hi)) == target,
        )
    )
    if state_id is not None:
        stmt = stmt.where(District.state_id == state_id)

    rows = db.execute(stmt).scalars().all()
    if len(rows) == 1:
        return rows[0], "district from name"
    if not rows:
        return None, "district name %r did not match any district" % cleaned
    return None, (
        "district name %r matches %d districts across states %s — a state is "
        "required to disambiguate it"
        % (cleaned, len(rows), sorted({r.state_id for r in rows}))
    )


def build_scope(
    db: Session,
    state_code: Optional[str] = None,
    state_name: Optional[str] = None,
    district_lgd_code: Optional[str] = None,
    district_name: Optional[str] = None,
) -> Scope:
    """Narrow to a state and, where possible, a district."""
    scope = Scope()

    state, note = resolve_state(db, state_code, state_name)
    if note:
        scope.notes.append(note)
    if state is not None:
        scope.state_id = state.state_id
        scope.state_code = state.state_code
        scope.state_name_en = state.state_name_en

    district, note = resolve_district(
        db, district_lgd_code, district_name, scope.state_id
    )
    if note:
        scope.notes.append(note)
    if district is not None:
        if scope.state_id is not None and district.state_id != scope.state_id:
            # Explicit contradiction between the two identities. Do not pick
            # a winner.
            scope.conflict = (
                "district %s belongs to state_id %s but state_id %s was "
                "supplied" % (district.lgd_district_code, district.state_id,
                              scope.state_id)
            )
            return scope
        scope.district_id = district.district_id
        scope.lgd_district_code = district.lgd_district_code
        scope.district_name_en = district.district_name_en
        if scope.state_id is None:
            # A district determines its state, so the state scope comes for
            # free and is authoritative rather than inferred from text.
            st = db.get(State, district.state_id)
            if st is not None:
                scope.state_id = st.state_id
                scope.state_code = st.state_code
                scope.state_name_en = st.state_name_en
                scope.notes.append("state derived from the resolved district")

    return scope


# ---------------------------------------------------------------------------
# Candidate queries — filtering happens in PostgreSQL, not in Python
# ---------------------------------------------------------------------------

_CANDIDATE_COLUMNS = (
    Constituency.id,
    Constituency.state_id,
    State.state_code,
    State.state_name_en,
    Constituency.ac_number,
    Constituency.constituency,
    Constituency.constituency_hindi,
    Constituency.district_id,
    District.district_name_en,
    District.district_name_hi,
    Constituency.lgd_district_code,
)


def _base_query():
    return (
        select(*_CANDIDATE_COLUMNS)
        .join(State, State.state_id == Constituency.state_id)
        .outerjoin(District, District.district_id == Constituency.district_id)
    )


def _apply_scope(stmt, scope: Scope):
    if scope.district_id is not None:
        return stmt.where(Constituency.district_id == scope.district_id)
    if scope.state_id is not None:
        return stmt.where(Constituency.state_id == scope.state_id)
    return stmt


def _rows_to_candidates(rows) -> list[Candidate]:
    return [Candidate(*row) for row in rows]


def _exact_matches(db: Session, name: str, scope: Scope) -> list[Candidate]:
    """Exact name match, evaluated in the database on both name columns."""
    target = _norm(name)
    if not target:
        return []
    stmt = _apply_scope(
        _base_query().where(
            or_(
                func.lower(func.trim(Constituency.constituency)) == target,
                func.lower(func.trim(Constituency.constituency_hindi)) == target,
            )
        ),
        scope,
    )
    return _rows_to_candidates(db.execute(stmt).all())


def _fuzzy_pool(db: Session, name: str, scope: Scope) -> tuple[list[Candidate], Optional[str]]:
    """The narrowed set fuzzy matching is allowed to consider."""
    if scope.state_id is not None:
        # At most 403 rows (Uttar Pradesh), typically far fewer.
        return _rows_to_candidates(
            db.execute(_apply_scope(_base_query(), scope)).all()
        ), None

    # No state scope. Narrow in SQL by the longest token of the input so the
    # query cannot degenerate into "load every constituency".
    cleaned = _strip_prefix(name, _AC_PREFIX)
    tokens = [t for t in re.split(r"\s+", cleaned) if len(t) >= 3]
    if not tokens:
        return [], (
            "no state or district scope, and %r has no token long enough to "
            "narrow the search safely" % cleaned
        )
    token = max(tokens, key=len)
    like = "%" + token.casefold() + "%"
    column = (Constituency.constituency_hindi if _is_devanagari(cleaned)
              else Constituency.constituency)
    stmt = (
        _base_query()
        .where(func.lower(column).like(like))
        .limit(_UNSCOPED_CANDIDATE_CAP + 1)
    )
    rows = db.execute(stmt).all()
    if len(rows) > _UNSCOPED_CANDIDATE_CAP:
        return [], (
            "no state or district scope, and %r matches more than %d "
            "constituencies — too broad to resolve safely"
            % (token, _UNSCOPED_CANDIDATE_CAP)
        )
    return _rows_to_candidates(rows), None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def resolve(
    db: Session,
    constituency_name: Optional[str],
    state_code: Optional[str] = None,
    state_name: Optional[str] = None,
    district_lgd_code: Optional[str] = None,
    district_name: Optional[str] = None,
) -> Resolution:
    """Resolve a constituency name within the strongest available scope."""
    cleaned = _strip_prefix(constituency_name, _AC_PREFIX)
    scope = build_scope(db, state_code, state_name,
                        district_lgd_code, district_name)

    if scope.conflict:
        return Resolution(
            status=UNRESOLVED_SCOPE_CONFLICT, scope=scope,
            reason=scope.conflict,
            required=["state_code", "district_lgd_code"],
        )

    if not cleaned:
        return Resolution(
            status=UNRESOLVED_NOT_FOUND, scope=scope,
            reason="no constituency name was supplied",
            required=["assembly_constituency_name"],
        )

    # ---- 3. exact name match inside the scope
    exact = _exact_matches(db, cleaned, scope)
    if len(exact) == 1:
        return Resolution(status=RESOLVED, scope=scope, match=exact[0],
                          method="exact", score=100.0,
                          reason="exact name match within %s scope" % scope.level)
    if len(exact) > 1:
        # Several rows share the name inside the scope. Never pick one.
        return Resolution(
            status=UNRESOLVED_AMBIGUOUS, scope=scope, candidates=exact,
            method="exact",
            reason="%d constituencies share the name %r within %s scope"
                   % (len(exact), cleaned, scope.level),
            required=(["district_lgd_code"] if scope.state_id is not None
                      else ["state_code", "district_lgd_code"]),
        )

    # ---- 4. fuzzy match, inside the scope only
    pool, why = _fuzzy_pool(db, cleaned, scope)
    if why:
        return Resolution(status=UNRESOLVED_SCOPE_REQUIRED, scope=scope,
                          reason=why, required=["state_code"])
    if not pool:
        # Unscoped, the candidate pool is narrowed in SQL by a token of the
        # input, so a misspelling finds nothing. That is safe but not the
        # caller's fault, so the hint says a scope would enable fuzzy matching.
        return Resolution(
            status=UNRESOLVED_NOT_FOUND, scope=scope,
            reason=("no constituency name contains %r; supply a state to "
                    "allow fuzzy matching" % cleaned
                    if scope.state_id is None else
                    "no constituency found for %r within %s scope"
                    % (cleaned, scope.level)),
            required=["state_code"] if scope.state_id is None else [],
        )

    devanagari = _is_devanagari(cleaned)
    keyed: list[tuple[str, Candidate]] = []
    for cand in pool:
        value = cand.constituency_hindi if devanagari else cand.constituency
        if value:
            keyed.append((unicodedata.normalize("NFC", value), cand))
    if not keyed:
        return Resolution(
            status=UNRESOLVED_NOT_FOUND, scope=scope,
            reason=("no %s constituency name is available to match against "
                    "within %s scope"
                    % ("Hindi" if devanagari else "English", scope.level)),
        )

    top = process.extract(
        unicodedata.normalize("NFC", cleaned),
        [k for k, _ in keyed],
        scorer=fuzz.partial_ratio,
        limit=5,
    )
    if not top or top[0][1] < _MATCH_THRESHOLD:
        return Resolution(
            status=UNRESOLVED_NOT_FOUND, scope=scope, method="fuzzy",
            score=(top[0][1] if top else 0.0),
            reason="best fuzzy score %.1f is below the threshold of %d"
                   % ((top[0][1] if top else 0.0), _MATCH_THRESHOLD),
        )

    # Preserved from the original behaviour: an exact tie at the top is
    # ambiguous, not a match. ("लखनऊ" ties against every "लखनऊ ..." AC.)
    tied = [t for t in top if t[1] == top[0][1]]
    tied_candidates = [keyed[t[2]][1] for t in tied]
    if len({(c.constituency_id) for c in tied_candidates}) > 1:
        return Resolution(
            status=UNRESOLVED_AMBIGUOUS, scope=scope, method="fuzzy",
            score=top[0][1], candidates=tied_candidates,
            reason="%d constituencies tie at fuzzy score %.1f within %s scope"
                   % (len(tied_candidates), top[0][1], scope.level),
            required=(["district_lgd_code"] if scope.state_id is not None
                      else ["state_code", "district_lgd_code"]),
        )

    match = tied_candidates[0]

    # Unscoped fuzzy is only safe when every plausible candidate belongs to a
    # single state. This is what stops a nationwide fuzzy match from silently
    # choosing another state's same-named AC.
    if scope.state_id is None:
        plausible = [keyed[t[2]][1] for t in top if t[1] >= _MATCH_THRESHOLD]
        states = {c.state_id for c in plausible}
        if len(states) > 1:
            return Resolution(
                status=UNRESOLVED_AMBIGUOUS, scope=scope, method="fuzzy",
                score=top[0][1], candidates=plausible,
                reason=("%r fuzzy-matches constituencies in %d different "
                        "States/UTs; a state is required to disambiguate"
                        % (cleaned, len(states))),
                required=["state_code"],
            )

    return Resolution(status=RESOLVED, scope=scope, match=match,
                      method="fuzzy", score=top[0][1],
                      reason="fuzzy match at %.1f within %s scope"
                             % (top[0][1], scope.level))


# ---------------------------------------------------------------------------
# Backwards-compatible wrapper
# ---------------------------------------------------------------------------

def resolve_constituency(
    db: Session,
    raw_value: str,
    state_name: Optional[str] = None,
    district_name: Optional[str] = None,
    state_code: Optional[str] = None,
    district_lgd_code: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Legacy signature kept for the OCR workers.

    Returns (constituency_hindi, district_name_hi) on a confident match, or
    (None, None) when unresolved — exactly as before. The state/district
    arguments are optional and additive, so existing two-argument callers keep
    working unchanged.
    """
    result = resolve(
        db, raw_value,
        state_code=state_code, state_name=state_name,
        district_lgd_code=district_lgd_code, district_name=district_name,
    )
    if not result.resolved or result.match is None:
        print("[constituency_resolver] unresolved %r -> %s: %s"
              % (raw_value, result.status, result.reason))
        return None, None

    m = result.match
    print("[constituency_resolver] %r -> %r (%s, score=%s, scope=%s, "
          "state=%s ac=%s)"
          % (raw_value, m.constituency_hindi or m.constituency, result.method,
             result.score, result.scope.level, m.state_code, m.ac_number))
    return (m.constituency_hindi or m.constituency), m.district_name_hi
