import json
import os
import re
import signal
import threading
import cv2
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.job import Job
from app.db.base_model import *

from app.core.image_processing import (
    download_image,
    crop_rois,
)

from app.core.qwen_ocr_client import run_qwen_ocr
from app.core.smart_parser import parse_smart
from app.core.constituency_resolver import resolve_constituency


POLL_INTERVAL = 3  # seconds

# Event set by signal handlers to stop the worker loop cleanly
_stop_event = threading.Event()


def _handle_shutdown(signum, frame):
    print(f"\n[STOP] Worker received signal {signum} - shutting down cleanly...")
    _stop_event.set()


def process_job(job: Job, db: Session):
    print(f"[START] Processing job: {job.id}")

    try:
        # 1. Download image
        print("[INFO] Downloading image...")
        image = download_image(job.image_path)
        print("[OK] Image downloaded")

        # 2. Process image
        if job.is_cropped:
            print("[INFO] Cropped image -> using as-is")
            processed = image
        else:
            print("[INFO] Not cropped -> ROI processing")

            top_left, form_section = crop_rois(image)

            w = max(top_left.shape[1], form_section.shape[1])
            top_left_resized = cv2.resize(top_left, (w, top_left.shape[0]))
            form_section_resized = cv2.resize(form_section, (w, form_section.shape[0]))

            processed = cv2.vconcat([top_left_resized, form_section_resized])

        # 3. Run Qwen OCR
        print("[INFO] Calling Qwen OCR...")
        qwen_json = run_qwen_ocr(processed)
        print("[INFO] Qwen JSON received")

        # 4. Map to expected parsed format
        def _fmt(val):
            return {"value": val if val else None, "confidence": 0.99 if val else 0.0}

        parsed = {
            "name": _fmt(qwen_json.get("voter_name")),
            "epic": _fmt(qwen_json.get("epic_number")),
            "mobile": _fmt(qwen_json.get("mobile_number")),
            "serial_number": _fmt(qwen_json.get("serial_number")),
            "part_number_and_name": _fmt(qwen_json.get("part_number_name")),
            "assembly_constituency": _fmt(qwen_json.get("constituency")),
            "district": _fmt(None),
            "state": _fmt(qwen_json.get("state")),
            "address": _fmt(qwen_json.get("address")),
        }
        
        # We need raw_text to remain for job.result backwards compatibility, we'll store JSON string
        ocr_text = json.dumps(qwen_json, ensure_ascii=False)

        if parsed.get("name", {}).get("value"):
            print("[OK] Qwen mapping succeeded")
        else:
            print("[WARN] Qwen mapping: name not found (partial result saved)")

        # 4b. Resolve constituency against DB
        ac_raw = parsed.get("assembly_constituency", {}).get("value")
        if ac_raw:
            # Scope the lookup with the State/District the parser already
            # extracted. Without this the match runs against all 3,551 ACs
            # and can land on a same-named constituency in another State.
            ac_hindi, district_hi = resolve_constituency(
                db,
                ac_raw,
                state_name=parsed.get("state", {}).get("value"),
                district_name=parsed.get("district", {}).get("value"),
            )
            if ac_hindi:
                parsed["assembly_constituency"]["value"] = ac_hindi
                parsed["assembly_constituency"]["confidence"] = 0.99
                if district_hi and not parsed.get("district", {}).get("value"):
                    district_hi = re.sub(r"^जिल[ाेोां]*\s*[:：]?\s*", "", district_hi).strip()
                    parsed.setdefault("district", {})["value"] = district_hi
                    parsed["district"]["confidence"] = 0.99
            else:
                # Resolver could not confirm (ambiguous or no match) — clear so
                # the user knows to retake the image for a cleaner constituency scan
                parsed["assembly_constituency"]["value"] = None
                parsed["assembly_constituency"]["confidence"] = 0.0

        # 5. Save result
        job.status = "completed"
        job.result = {
            "raw_text": ocr_text,
            "parsed": parsed,
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

    # Register signal handlers so PaddlePaddle's C++ backend gets a chance
    # to release resources before the process exits — prevents crashes on
    # Ctrl+C or terminal close on macOS
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