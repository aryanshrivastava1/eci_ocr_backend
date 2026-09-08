"""
Reproducible reference-data importer for `districts` and `constituency`.

The project has no Alembic migrations — `Base.metadata.create_all()` creates
these tables empty at startup and nothing ever fills them. This script is the
reproducible way to populate them from an authoritative CSV export.

It ships with NO data. You supply the CSVs.

Design rules:
  - districts are imported before constituencies (FK direction)
  - the whole import runs in ONE transaction: a failure anywhere leaves the
    database exactly as it was, so constituency/district mappings can never be
    left half-written
  - idempotent: re-running with the same CSV inserts nothing and updates only
    genuinely changed fields
  - a constituency whose district cannot be resolved ABORTS the import; it is
    never inserted with a null or guessed district_id
  - dry-run by default. Nothing is written unless you pass --apply.

Usage:
    python -m scripts.seed_reference_data \
        --districts data/districts.csv \
        --constituencies data/constituencies.csv          # dry run, no writes

    python -m scripts.seed_reference_data \
        --districts data/districts.csv \
        --constituencies data/constituencies.csv --apply  # writes

    python -m scripts.seed_reference_data --verify         # counts only

CSV formats are documented in load_districts() and load_constituencies().
"""

import argparse
import csv
import os
import sys

# Allow `python scripts/seed_reference_data.py` as well as `python -m scripts...`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.db.base_model import *  # noqa: E402,F401,F403  (registers all models)
from app.models.constituency import Constituency  # noqa: E402
from app.models.districts import District  # noqa: E402


class SeedError(Exception):
    """Any validation failure. Always aborts the transaction."""


# ---------------------------------------------------------------------------
# CSV loading + validation
# ---------------------------------------------------------------------------

def _read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise SeedError(f"CSV not found: {path}")
    # utf-8-sig strips the BOM Excel writes, which would otherwise corrupt the
    # first header name.
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SeedError(f"CSV has no data rows: {path}")
    return rows


def _require_columns(rows: list[dict], required: set[str], path: str) -> None:
    present = {(c or "").strip() for c in rows[0].keys()}
    missing = required - present
    if missing:
        raise SeedError(
            f"{path}: missing required column(s): {', '.join(sorted(missing))}\n"
            f"  found: {', '.join(sorted(present))}"
        )


def _clean(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _norm(v: str) -> str:
    """Natural-key normalisation: case- and whitespace-insensitive."""
    return " ".join(v.split()).casefold()


def load_districts(path: str) -> list[dict]:
    """
    Expected CSV columns:

        district_name_en   (required, non-empty) — natural key
        district_name_hi   (required, non-empty)
        mandala_id         (optional, integer)   — division id; needed by
                                                   auth_service for non-superadmin roles
        district_id        (optional, integer)   — force an explicit PK instead
                                                   of the sequence
    """
    rows = _read_csv(path)
    _require_columns(rows, {"district_name_en", "district_name_hi"}, path)

    out, seen = [], {}
    for i, row in enumerate(rows, start=2):  # line 1 is the header
        en = _clean(row, "district_name_en")
        hi = _clean(row, "district_name_hi")
        if not en:
            raise SeedError(f"{path}:{i} district_name_en is empty")
        if not hi:
            raise SeedError(f"{path}:{i} district_name_hi is empty")

        key = _norm(en)
        if key in seen:
            raise SeedError(
                f"{path}:{i} duplicate district_name_en '{en}' "
                f"(first seen on line {seen[key]})"
            )
        seen[key] = i

        rec = {"district_name_en": en, "district_name_hi": hi,
               "mandala_id": None, "district_id": None, "_line": i}

        for col in ("mandala_id", "district_id"):
            raw = _clean(row, col)
            if raw:
                if not raw.lstrip("-").isdigit():
                    raise SeedError(f"{path}:{i} {col} must be an integer, got '{raw}'")
                rec[col] = int(raw)

        out.append(rec)
    return out


def load_constituencies(path: str) -> list[dict]:
    """
    Expected CSV columns:

        constituency        (required, non-empty) — English name; natural key
        constituency_hindi  (required, non-empty) — the name OCR matches against
        district_name_en    (required, non-empty) — resolved to districts.district_id

    Note: the DB column `District` (NOT NULL) is filled from the resolved
    district's English name; do not supply it separately.
    """
    rows = _read_csv(path)
    _require_columns(
        rows, {"constituency", "constituency_hindi", "district_name_en"}, path
    )

    out, seen_en, seen_hi = [], {}, {}
    for i, row in enumerate(rows, start=2):
        en = _clean(row, "constituency")
        hi = _clean(row, "constituency_hindi")
        dis = _clean(row, "district_name_en")

        if not en:
            raise SeedError(f"{path}:{i} constituency is empty")
        if not hi:
            raise SeedError(f"{path}:{i} constituency_hindi is empty")
        if not dis:
            raise SeedError(f"{path}:{i} district_name_en is empty")

        k_en = _norm(en)
        if k_en in seen_en:
            raise SeedError(
                f"{path}:{i} duplicate constituency '{en}' "
                f"(first seen on line {seen_en[k_en]})"
            )
        seen_en[k_en] = i

        # Hindi collisions are fatal: resolve_constituency() and /voter/save both
        # match on this column, so a duplicate makes lookups ambiguous.
        k_hi = _norm(hi)
        if k_hi in seen_hi:
            raise SeedError(
                f"{path}:{i} duplicate constituency_hindi '{hi}' "
                f"(first seen on line {seen_hi[k_hi]}) — "
                f"OCR matching requires this to be unique"
            )
        seen_hi[k_hi] = i

        out.append({"constituency": en, "constituency_hindi": hi,
                    "district_name_en": dis, "_line": i})
    return out


# ---------------------------------------------------------------------------
# Upserts — matched on natural keys, since the schema has no unique constraints
# ---------------------------------------------------------------------------

def upsert_districts(db, records: list[dict]) -> dict:
    stats = {"inserted": 0, "updated": 0, "unchanged": 0}

    existing = {_norm(d.district_name_en or ""): d for d in db.query(District).all()}

    for rec in records:
        row = existing.get(_norm(rec["district_name_en"]))
        if row is None:
            row = District(
                district_name_en=rec["district_name_en"],
                district_name_hi=rec["district_name_hi"],
                mandala_id=rec["mandala_id"],
            )
            if rec["district_id"] is not None:
                row.district_id = rec["district_id"]
            db.add(row)
            db.flush()  # assign PK now; constituencies need it in this same txn
            existing[_norm(rec["district_name_en"])] = row
            stats["inserted"] += 1
            continue

        changed = False
        if row.district_name_hi != rec["district_name_hi"]:
            row.district_name_hi = rec["district_name_hi"]
            changed = True
        if rec["mandala_id"] is not None and row.mandala_id != rec["mandala_id"]:
            row.mandala_id = rec["mandala_id"]
            changed = True
        stats["updated" if changed else "unchanged"] += 1

    return stats


def upsert_constituencies(db, records: list[dict]) -> dict:
    stats = {"inserted": 0, "updated": 0, "unchanged": 0}

    districts = {_norm(d.district_name_en or ""): d for d in db.query(District).all()}
    existing = {_norm(c.constituency or ""): c for c in db.query(Constituency).all()}

    # Resolve every district BEFORE writing anything, so an unresolved mapping
    # aborts with a complete list rather than after a partial write.
    unresolved = [
        f"  line {r['_line']}: '{r['constituency']}' -> district "
        f"'{r['district_name_en']}' not found in districts"
        for r in records if _norm(r["district_name_en"]) not in districts
    ]
    if unresolved:
        raise SeedError(
            f"{len(unresolved)} constituency row(s) have an unresolved district. "
            f"Import districts first, or fix the spelling:\n" + "\n".join(unresolved)
        )

    for rec in records:
        district = districts[_norm(rec["district_name_en"])]
        if district.district_id is None:
            raise SeedError(
                f"line {rec['_line']}: district '{district.district_name_en}' "
                f"has no district_id"
            )

        row = existing.get(_norm(rec["constituency"]))
        if row is None:
            db.add(Constituency(
                constituency=rec["constituency"],
                constituency_hindi=rec["constituency_hindi"],
                district=district.district_name_en,   # NOT NULL column
                district_id=district.district_id,
            ))
            stats["inserted"] += 1
            continue

        changed = False
        for attr, value in (
            ("constituency_hindi", rec["constituency_hindi"]),
            ("district", district.district_name_en),
            ("district_id", district.district_id),
        ):
            if getattr(row, attr) != value:
                setattr(row, attr, value)
                changed = True
        stats["updated" if changed else "unchanged"] += 1

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def verify(db) -> None:
    d = db.query(District).count()
    c = db.query(Constituency).count()
    orphans = (
        db.query(Constituency)
        .outerjoin(District, Constituency.district_id == District.district_id)
        .filter(District.district_id.is_(None))
        .count()
    )
    dupes = (
        db.query(func.lower(Constituency.constituency_hindi), func.count("*"))
        .group_by(func.lower(Constituency.constituency_hindi))
        .having(func.count("*") > 1)
        .count()
    )
    print(f"  districts            : {d}")
    print(f"  constituency         : {c}")
    print(f"  orphaned constituency: {orphans}   (must be 0)")
    print(f"  duplicate hindi names: {dupes}   (must be 0)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Import districts and constituencies from CSV (districts first)."
    )
    ap.add_argument("--districts", help="path to districts CSV")
    ap.add_argument("--constituencies", help="path to constituencies CSV")
    ap.add_argument("--apply", action="store_true",
                    help="commit the transaction (default is a dry run)")
    ap.add_argument("--verify", action="store_true",
                    help="print current row counts and integrity checks, then exit")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.verify:
            print("Current reference data:")
            verify(db)
            return 0

        if not args.districts and not args.constituencies:
            ap.error("provide --districts and/or --constituencies, or --verify")

        # Parse and validate both files up front — no DB writes yet.
        district_rows = load_districts(args.districts) if args.districts else []
        constituency_rows = (
            load_constituencies(args.constituencies) if args.constituencies else []
        )
        print(f"Parsed {len(district_rows)} district row(s), "
              f"{len(constituency_rows)} constituency row(s)")

        d_stats = c_stats = None
        try:
            # districts first — constituencies resolve their FK against them
            if district_rows:
                d_stats = upsert_districts(db, district_rows)
                db.flush()
            if constituency_rows:
                c_stats = upsert_constituencies(db, constituency_rows)
                db.flush()

            if args.apply:
                db.commit()
                print("\nCOMMITTED")
            else:
                db.rollback()
                print("\nDRY RUN — rolled back. Re-run with --apply to write.")
        except Exception:
            db.rollback()
            raise

        if d_stats:
            print(f"  districts    : +{d_stats['inserted']} inserted, "
                  f"{d_stats['updated']} updated, {d_stats['unchanged']} unchanged")
        if c_stats:
            print(f"  constituency : +{c_stats['inserted']} inserted, "
                  f"{c_stats['updated']} updated, {c_stats['unchanged']} unchanged")

        if args.apply:
            print("\nPost-import state:")
            verify(db)
        return 0

    except SeedError as e:
        print(f"\nABORTED — nothing was written.\n{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nABORTED — nothing was written.\n{type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
