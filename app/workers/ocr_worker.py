import signal
import threading

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.job import Job
from app.db.base_model import *

from app.core.image_processing import download_image, prepare_for_ocr
from app.core.qwen_ocr_client import run_qwen_ocr
from app.core.constituency_resolver import resolve_constituency
from app.core.extraction_schema import FIELDS, LEGACY_KEYS
from app.core.field_validation import (
    DB_CONFIRMED_CONFIDENCE,
    NEEDS_REVIEW,
    VERIFIED,
    REVIEWABLE,
    validate,
)

POLL_INTERVAL = 3  # seconds

# Event set by signal handlers to stop the worker loop cleanly
_stop_event = threading.Event()


def _handle_shutdown(signum, frame):
    print(f"\n[STOP] Worker received signal {signum} - shutting down cleanly...")
    _stop_event.set()


def build_parsed(model_fields: dict) -> dict:
    """
    Map the model's response onto the schema and validate every field.

    FIELDS is exactly the eight keys the app saves (plus the DB-derived
    district), so `parsed` never carries fields the app has no use for.
    """
    raw = dict(model_fields or {})

    parsed = {}
    for spec in FIELDS:
        parsed[spec.key] = validate(spec.key, raw.get(spec.model_key))

    ordered = {k: parsed[k] for k in LEGACY_KEYS if k in parsed}
    ordered.update({k: v for k, v in parsed.items() if k not in ordered})
    return ordered


def apply_constituency_resolution(parsed: dict, db: Session) -> None:
    """
    Annotate the constituency (and district) against the reference table.

    Non-destructive by construction: the OCR value stays in place no matter
    what the resolver concludes. A confirmed match is recorded alongside it as
    `db_match`, and only a confirmed match may fill an EMPTY district.
    """
    ac = parsed.get("assembly_constituency") or {}
    ac_value = ac.get("value")
    if not ac_value:
        return

    match = resolve_constituency(db, ac_value)

    ac["db_match"] = match.matched
    ac["db_score"] = match.score
    ac["db_status"] = match.status

    if match.status == "confirmed":
        # A reference-table hit IS a real check, so this is the one path on
        # which a free-text field earns "verified".
        ac["status"] = VERIFIED
        ac["confidence"] = DB_CONFIRMED_CONFIDENCE
        ac["note"] = None
    else:
        # Value preserved; the operator is told it was not DB-validated.
        ac["status"] = NEEDS_REVIEW
        ac["confidence"] = min(ac.get("confidence", 0.45), 0.45)
        ac["note"] = match.note

    district = parsed.get("district") or {}
    if match.status == "confirmed" and match.district and not district.get("value"):
        district.update({
            "value": match.district,
            "confidence": DB_CONFIRMED_CONFIDENCE,
            "source": "db",
            "status": "verified",
            "note": f"derived from constituency '{match.matched}'",
        })
        parsed["district"] = district


def process_job(job: Job, db: Session):
    print(f"[START] Processing job: {job.id}")

    try:
        # 1. Download image
        print("[INFO] Downloading image...")
        image = download_image(job.image_path)
        print(f"[OK] Image downloaded ({image.shape[1]}x{image.shape[0]})")

        # 2. Preprocess — full page, layout preserved, no cropping
        processed = prepare_for_ocr(image)
        print(f"[INFO] Sending full page {processed.shape[1]}x{processed.shape[0]} "
              f"(cropped_upload={job.is_cropped})")

        # 3. Run Qwen OCR — the verbatim response comes back with the fields
        print("[INFO] Calling Qwen OCR...")
        ocr = run_qwen_ocr(processed)
        print(f"[INFO] Qwen response received "
              f"({len(ocr.raw_text)} chars, mode={ocr.parse_mode})")
        if ocr.parse_error:
            print(f"[WARN] {ocr.parse_error}")

        # 4. Map onto the schema and validate every field
        parsed = build_parsed(ocr.fields)

        # 4b. Annotate against the reference table — never overwrite OCR
        apply_constituency_resolution(parsed, db)

        flagged = [k for k, v in parsed.items() if v.get("status") in REVIEWABLE]
        if parsed.get("name", {}).get("value"):
            print(f"[OK] Extraction complete"
                  + (f" — confirm: {', '.join(flagged)}" if flagged else ""))
        else:
            print("[WARN] Voter name not found (partial result saved)")

        # 5. Save result — the exact model response is preserved verbatim
        job.status = "completed"
        job.result = {
            "raw_text": ocr.raw_text,
            "parsed": parsed,
            "ocr_meta": ocr.as_dict(),
        }

    except Exception as e:
        print(f"[ERROR]: {str(e)}")
        job.status = "failed"
        job.error_message = str(e)

    db.commit()

    print(f"[DONE] Job finished: {job.id} -> {job.status}")


def worker():
    # Force line-buffered stdout so logs appear immediately in the terminal
    # even when running as a child process (multiprocessing.Process buffers
    # output by default)
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    print("Worker started...", flush=True)

    # Qwen OCR is a remote service; no warmup needed locally.

    try:
        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)
    except (OSError, ValueError):
        pass

    while not _stop_event.is_set():
        db: Session = SessionLocal()

        try:
            job = (
                db.query(Job)
                .filter(Job.status == "pending")
                .order_by(Job.created_at.asc())
                .first()
            )

            if not job:
                print("[IDLE] No pending jobs...")
            else:
                job.status = "processing"
                db.commit()
                db.refresh(job)

                try:
                    process_job(job, db)

                except Exception as e:
                    print(f"[ERROR] Error processing job {job.id}: {str(e)}")
                    db.rollback()
                    job.status = "failed"
                    job.error_message = str(e)
                    db.commit()

        except Exception as e:
            print(f"[ERROR] Database error in worker loop: {str(e)}")

        finally:
            try:
                db.close()
            except Exception as e:
                print(f"[ERROR] Error closing database session: {str(e)}")

        _stop_event.wait(timeout=POLL_INTERVAL)

    print("[OK] Worker stopped cleanly")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)  # required on macOS
    worker()
