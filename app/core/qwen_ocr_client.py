"""
Qwen OCR transport.

Two guarantees this module now makes:

  1. The EXACT model response is always returned to the caller and always
     persisted, whether parsing succeeded, partly succeeded, or failed. The
     previous version read `raw_markdown`, parsed it, discarded it, and stored
     a re-serialised parse under the name `raw_text` — which made every bad
     extraction undiagnosable after the fact.

  2. A response the strict JSON path cannot read is no longer a dead job. The
     ladder degrades: strict JSON → fenced JSON → embedded JSON object →
     parse_smart() on markdown/HTML → raw text preserved for review.
"""

import json
import re

import cv2
import numpy as np
import requests

from app.core.config import settings
from app.core.extraction_schema import build_prompt


class QwenResult:
    """
    Everything one OCR call produced.

    fields      parsed key/value dict from the model ({} if nothing parsed)
    raw_text    the model's response, verbatim — always populated
    parse_mode  which rung of the ladder succeeded
    parse_error why strict parsing failed, if it did
    http_status transport status code
    """

    def __init__(self, fields, raw_text, parse_mode, parse_error=None,
                 http_status=None, endpoint=None):
        self.fields = fields or {}
        self.raw_text = raw_text or ""
        self.parse_mode = parse_mode
        self.parse_error = parse_error
        self.http_status = http_status
        self.endpoint = endpoint

    def as_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "parse_mode": self.parse_mode,
            "parse_error": self.parse_error,
            "http_status": self.http_status,
            "endpoint": self.endpoint,
        }


def _strip_fence(s: str) -> str:
    s = s.strip()
    m = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", s, re.DOTALL)
    return m.group(1).strip() if m else s


def _embedded_object(s: str):
    """Recover the outermost {...} from prose or a truncated response."""
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except ValueError:
                    return None
    return None


def _parse_response_text(raw: str) -> tuple[dict, str, str | None]:
    """Ladder: strict → fenced → embedded object → parse_smart → nothing."""
    if not raw or not raw.strip():
        return {}, "empty", "model returned an empty response"

    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict):
            return data, "json_strict", None
    except ValueError:
        pass

    try:
        data = json.loads(_strip_fence(raw))
        if isinstance(data, dict):
            return data, "json_fenced", None
    except ValueError:
        pass

    data = _embedded_object(raw)
    if isinstance(data, dict):
        return data, "json_embedded", "JSON recovered from surrounding text"

    # Markdown/HTML response — fall back to the layout-aware parser.
    if "<td" in raw or "<table" in raw or ":" in raw:
        from app.core.smart_parser import parse_smart

        parsed = parse_smart(raw)
        fields = {
            "voter_name": (parsed.get("name") or {}).get("value"),
            "epic_number": (parsed.get("epic") or {}).get("value"),
            "address": (parsed.get("address") or {}).get("value"),
            "serial_number": (parsed.get("serial_number") or {}).get("value"),
            "part_number_name": (parsed.get("part_number_and_name") or {}).get("value"),
            "constituency": (parsed.get("assembly_constituency") or {}).get("value"),
            "state": (parsed.get("state") or {}).get("value"),
            "mobile_number": (parsed.get("mobile") or {}).get("value"),
            "district": (parsed.get("district") or {}).get("value"),
        }
        fields = {k: v for k, v in fields.items() if v}
        if fields:
            return fields, "smart_parser_fallback", "response was not JSON; regex fallback used"

    return {}, "unparsed", "response could not be parsed as JSON or as a form layout"


def run_qwen_ocr(image: np.ndarray) -> QwenResult:
    """
    Send a preprocessed BGR image to the Qwen OCR service.

    Raises only on transport failure. A response that arrives but cannot be
    parsed comes back as a QwenResult with empty `fields` and the raw text
    preserved, so the job completes as reviewable rather than dying.
    """
    endpoint = settings.QWEN_OCR_API_URL
    if not endpoint:
        raise ValueError("QWEN_OCR_API_URL is not configured in environment.")

    success, encoded_image = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not success:
        raise RuntimeError("Failed to encode image to JPEG.")

    try:
        response = requests.post(
            endpoint,
            files={"file": ("image.jpg", encoded_image.tobytes(), "image/jpeg")},
            # Ignored by endpoints that don't accept it; keeps the notebook's
            # prompt and this repo's schema aligned for those that do.
            data={"prompt": build_prompt()},
            timeout=180,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to connect to Qwen OCR API: {str(e)}")

    status = response.status_code

    # The service wraps the model output; if it doesn't, treat the body as the
    # model output directly. Either way the verbatim text is what we keep.
    try:
        envelope = response.json()
    except ValueError:
        raw_text = response.text
        fields, mode, err = _parse_response_text(raw_text)
        return QwenResult(fields, raw_text, mode, err, status, endpoint)

    if isinstance(envelope, dict) and envelope.get("success") is False:
        raise RuntimeError(f"Qwen OCR API error: {envelope.get('error', 'Unknown error')}")

    if isinstance(envelope, dict):
        raw_text = (
            envelope.get("raw_markdown")
            or envelope.get("text")
            or envelope.get("ocr_text")
            or ""
        )
        if not raw_text:
            # The service already returned structured fields.
            payload = envelope.get("data") if isinstance(envelope.get("data"), dict) else envelope
            raw_text = json.dumps(envelope, ensure_ascii=False)
            return QwenResult(payload, raw_text, "service_structured", None, status, endpoint)
    else:
        raw_text = json.dumps(envelope, ensure_ascii=False)

    fields, mode, err = _parse_response_text(raw_text)
    return QwenResult(fields, raw_text, mode, err, status, endpoint)
