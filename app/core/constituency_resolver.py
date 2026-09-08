"""
Match a raw OCR constituency string against the reference table.

This resolver PROPOSES; it never disposes. It returns a candidate and a score,
and the caller keeps the OCR value regardless. The previous version returned
(None, None) on an ambiguous match, an absent match, or an empty reference
table — and the workers then nulled a value the model had read correctly.

Two other changes:
  - token_set_ratio replaces partial_ratio. partial_ratio scores a substring as
    a perfect match, so "लखनऊ" tied at 100 against every "लखनऊ ..." row and the
    tie-guard threw the value away.
  - the reference table is cached instead of being re-read on every job.
"""

import re
import threading
import time

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.models.constituency import Constituency
from app.models.districts import District

# Accept outright at or above this; propose for review between REVIEW and this.
_ACCEPT_THRESHOLD = 88
_REVIEW_THRESHOLD = 60

_CACHE_TTL = 300  # seconds
_cache: dict = {"at": 0.0, "rows": None}
_cache_lock = threading.Lock()


class ConstituencyMatch:
    """
    matched      canonical Hindi name, or None
    district     district name in Hindi, or None
    score        0-100 similarity
    status       "confirmed" | "candidate" | "unmatched"
    note         why it isn't confirmed, for the operator
    """

    def __init__(self, matched=None, district=None, score=0.0,
                 status="unmatched", note=None):
        self.matched = matched
        self.district = district
        self.score = round(float(score), 1)
        self.status = status
        self.note = note


def _normalise(v: str) -> str:
    """Fold OCR noise that shouldn't affect matching."""
    v = re.sub(r"[^\w\sऀ-ॿ]", " ", v)
    v = v.replace("ं", "ं")  # keep anusvara; placeholder for future folds
    return re.sub(r"\s+", " ", v).strip()


def _load_rows(db: Session):
    now = time.monotonic()
    with _cache_lock:
        if _cache["rows"] is not None and now - _cache["at"] < _CACHE_TTL:
            return _cache["rows"]
    # Cache plain tuples, not ORM instances: a Constituency object is bound to
    # the session that loaded it, and every attribute read after that session
    # closes raises DetachedInstanceError.
    rows = [
        (c.constituency_hindi, c.district_id)
        for c in db.query(
            Constituency.constituency_hindi, Constituency.district_id
        ).all()
    ]
    with _cache_lock:
        _cache["rows"] = rows
        _cache["at"] = now
    return rows


def resolve_constituency(db: Session, raw_value: str) -> ConstituencyMatch:
    """
    Fuzzy-match a raw OCR constituency against the reference table.

    Always returns a ConstituencyMatch. Never signals "delete the OCR value" —
    the caller is responsible for keeping it.
    """
    if not raw_value or not raw_value.strip():
        return ConstituencyMatch(status="unmatched", note="no OCR value to match")

    rows = _load_rows(db)
    if not rows:
        # This is a deployment problem, not a data-quality problem. Say so
        # loudly, and leave the OCR value untouched.
        print("[constituency_resolver] reference table is EMPTY — cannot validate. "
              "Seed the `constituency` table; keeping the OCR value as-is.")
        return ConstituencyMatch(
            status="unmatched",
            note="constituency reference table is empty — value not DB-validated",
        )

    names = [name for name, _ in rows if name]
    query = _normalise(raw_value)

    top = process.extract(query, names, scorer=fuzz.token_set_ratio, limit=5)
    if not top:
        return ConstituencyMatch(status="unmatched", note="no candidates")

    best_name, best_score, _ = top[0]
    tied = [n for n, s, _ in top if s == best_score]

    if len(tied) > 1:
        return ConstituencyMatch(
            score=best_score, status="candidate",
            note=f"ambiguous — {len(tied)} equal matches ({', '.join(tied[:3])}); "
                 f"OCR value kept, needs confirmation",
        )

    if best_score < _REVIEW_THRESHOLD:
        return ConstituencyMatch(
            score=best_score, status="unmatched",
            note=f"no close match in reference table (best {best_score:.0f})",
        )

    row = next((r for r in rows if r[0] == best_name), None)
    if row is None:
        return ConstituencyMatch(score=best_score, status="unmatched")
    _, district_id = row

    # A district lookup failure must never cost us the constituency match.
    district_hi = None
    try:
        district = (
            db.query(District)
            .filter(District.district_id == district_id)
            .first()
        )
        if district:
            district_hi = district.district_name_hi or district.district_name_en
            if district_hi:
                district_hi = re.sub(r"^जिल[ाेोां]*\s*[:：]?\s*",
                                     "", district_hi).strip()
    except Exception as e:
        print(f"[constituency_resolver] district lookup failed ({e}); "
              f"keeping constituency match without district")

    if best_score >= _ACCEPT_THRESHOLD:
        print(f"[constituency_resolver] '{raw_value}' -> '{best_name}' "
              f"(score={best_score:.0f}, district='{district_hi}')")
        return ConstituencyMatch(best_name, district_hi, best_score, "confirmed")

    print(f"[constituency_resolver] '{raw_value}' ~ '{best_name}' "
          f"(score={best_score:.0f}) — proposed, not confirmed")
    return ConstituencyMatch(
        best_name, district_hi, best_score, "candidate",
        note=f"closest match '{best_name}' scored {best_score:.0f} — confirm before saving",
    )
