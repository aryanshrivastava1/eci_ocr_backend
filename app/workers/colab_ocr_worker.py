import os
import re
import signal
import cv2
import numpy as np
import requests
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.job import Job
from app.db.base_model import *

from app.core.image_processing import download_image, prepare_for_ocr
from app.core.smart_parser import parse_smart
from app.core.field_validation import REVIEWABLE
# Both workers share one mapping/validation/resolution path so they cannot
# drift apart again.
from app.workers.ocr_worker import apply_constituency_resolution, build_parsed

import threading

POLL_INTERVAL = 3  # seconds

# Set COLAB_OCR_URL in .env — e.g. https://xxxx.ngrok.io/ocr
# Set COLAB_OCR_TIMEOUT to override the default 120s request timeout
COLAB_OCR_URL = os.getenv("COLAB_OCR_URL")
COLAB_TIMEOUT = int(os.getenv("COLAB_OCR_TIMEOUT", 120))

_stop_event = threading.Event()


def _handle_shutdown(signum, frame):
    print(f"\n🛑 Colab worker received signal {signum} — shutting down cleanly...")
    _stop_event.set()


def _call_colab_ocr(image: np.ndarray) -> str:
    """
    Encode the preprocessed BGR image as JPEG and POST it to the Colab FastAPI server.

    Expected Colab endpoint contract:
      POST /ocr
      Body: multipart/form-data, field name "file"
      Response JSON: {"success": true, "raw_markdown": "<ocr html/markdown>"}
    """
    if not COLAB_OCR_URL:
        raise RuntimeError("COLAB_OCR_URL is not set — add it to .env")

    ok, buf = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("Failed to encode image as JPEG")

    response = requests.post(
        COLAB_OCR_URL,
        files={"file": ("image.jpg", buf.tobytes(), "image/jpeg")},
        timeout=COLAB_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()

    if not data.get("success", True):
        raise RuntimeError(f"Colab OCR error: {data.get('error', 'unknown')}")

    # raw_markdown preserves <table>/<td>/<th> tags that parse_smart() needs
    ocr_text = data.get("raw_markdown") or data.get("text") or data.get("ocr_text") or ""
    if not ocr_text:
        raise RuntimeError(f"Colab response has no OCR text — got keys: {list(data.keys())}")

    return ocr_text


def process_job(job: Job, db: Session):
    print(f"🚀 Processing job via Colab: {job.id}")

    try:
        # 1. Download image from Supabase Storage URL
        print("⬇️ Downloading image...")
        image = download_image(job.image_path)
        print("✅ Image downloaded")

        # 2. Preprocess — full page, layout preserved, no cropping
        processed = prepare_for_ocr(image)
        print(f"🖼️ Sending full page {processed.shape[1]}x{processed.shape[0]} "
              f"(cropped_upload={job.is_cropped})")

        # 3. Hit the Colab OCR server
        print(f"🌐 Sending image to Colab ({COLAB_OCR_URL})...")
        ocr_text = _call_colab_ocr(processed)
        print(f"📄 OCR text received ({len(ocr_text)} chars)")

        # 4. Parse OCR output, then run the SAME mapping + validation as the
        #    Qwen worker so the two paths produce identical shapes.
        smart = parse_smart(ocr_text)
        model_fields = {
            "voter_name": (smart.get("name") or {}).get("value"),
            "epic_number": (smart.get("epic") or {}).get("value"),
            "address": (smart.get("address") or {}).get("value"),
            "serial_number": (smart.get("serial_number") or {}).get("value"),
            "part_number_name": (smart.get("part_number_and_name") or {}).get("value"),
            "constituency": (smart.get("assembly_constituency") or {}).get("value"),
            "state": (smart.get("state") or {}).get("value"),
            "district": (smart.get("district") or {}).get("value"),
            "mobile_number": (smart.get("mobile") or {}).get("value"),
        }
        parsed = build_parsed(model_fields)
        for f in parsed.values():
            f["source"] = "regex"

        # 4b. Annotate against the reference table — never overwrite OCR
        apply_constituency_resolution(parsed, db)

        flagged = [k for k, v in parsed.items() if v.get("status") in REVIEWABLE]
        if parsed.get("name", {}).get("value"):
            print("✅ Parser succeeded"
                  + (f" — confirm: {', '.join(flagged)}" if flagged else ""))
        else:
            print("⚠️ Parser: name not found (partial result saved)")

        # 5. Persist result — raw OCR text preserved verbatim
        job.status = "completed"
        job.result = {
            "raw_text": ocr_text,
            "parsed": parsed,
            "ocr_meta": {
                "raw_text": ocr_text,
                "parse_mode": "smart_parser",
                "parse_error": None,
                "http_status": None,
                "endpoint": COLAB_OCR_URL,
            },
        }

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        job.status = "failed"
        job.error_message = str(e)

    db.commit()
    print(f"🏁 Job finished: {job.id} → {job.status}")


def worker():
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    print(f"🚀 Colab OCR worker started (endpoint: {COLAB_OCR_URL or 'NOT SET'})...", flush=True)

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
                print("😴 No pending jobs...")
                _stop_event.wait(timeout=POLL_INTERVAL)
                continue

            job.status = "processing"
            db.commit()
            db.refresh(job)

            try:
                process_job(job, db)
            except Exception as e:
                print(f"❌ Error processing job {job.id}: {str(e)}")
                db.rollback()
                job.status = "failed"
                job.error_message = str(e)
                db.commit()

        finally:
            db.close()

        _stop_event.wait(timeout=POLL_INTERVAL)

    print("✅ Colab worker stopped cleanly")


if __name__ == "__main__":
    worker()
