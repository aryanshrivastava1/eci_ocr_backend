"""
Per-field normalisation and validation.

This is where field knowledge lives — not inside regex lookaheads.

The output envelope is additive: `value` and `confidence` keep the exact shape
the Flutter client already reads, and the new keys sit alongside them.

    {
      "value":      normalised value, or the raw model text when it failed
                    validation (a value is NEVER dropped),
      "confidence": derived from `status` — never a fabricated constant,
      "raw":        exactly what the model returned,
      "source":     "model" | "regex" | "db" | "derived",
      "status":     "verified" | "unverified" | "needs_review" | "missing",
      "note":       why it needs review, for the operator
    }

Governing rule for the whole pipeline: a later stage may add a candidate,
lower a status, or annotate a note. It may never overwrite or null a value
that came from OCR.
"""

import re

from app.core.extraction_schema import BY_KEY

VERIFIED = "verified"          # a real format/reference check passed
UNVERIFIED = "unverified"      # free text: no automatic check is possible
NEEDS_REVIEW = "needs_review"  # a check ran and FAILED
MISSING = "missing"

# Free text can never be "verified" by this module: nothing here can tell a
# correct Devanagari name from a plausibly-garbled one. Reporting 0.95 for
# those was the reason a wrong value looked trustworthy in the app.
_CONFIDENCE = {VERIFIED: 0.95, UNVERIFIED: 0.70, NEEDS_REVIEW: 0.45, MISSING: 0.0}

#: Statuses the operator must eyeball before saving.
REVIEWABLE = (UNVERIFIED, NEEDS_REVIEW)

# Confidence for a value additionally confirmed against a reference table.
DB_CONFIRMED_CONFIDENCE = 0.99


def field(value, *, raw=None, source="model", status=VERIFIED, note=None, confidence=None):
    """Build a field envelope."""
    if value in (None, ""):
        status = MISSING
    return {
        "value": value if value not in (None, "") else None,
        "confidence": confidence if confidence is not None else _CONFIDENCE[status],
        "raw": raw,
        "source": source,
        "status": status,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _clean_text(v) -> str | None:
    if v is None:
        return None
    v = str(v)
    v = re.sub(r"\*+|`+", "", v)          # markdown artefacts
    v = re.sub(r"\s+", " ", v).strip()
    v = v.strip(":-–—, ")
    return v or None


def _digits(v: str) -> str:
    return re.sub(r"\D", "", str(v).translate(_DEVANAGARI_DIGITS))


_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6), (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4), (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2), (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def _verhoeff_ok(number: str) -> bool:
    """Aadhaar's checksum. A 12-digit string that fails this is a misread."""
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


_EPIC_PATTERNS = (
    r"^[A-Z]{3}\d{7}$",              # XGF0739839
    r"^[A-Z]{2}\d{8}$",              # AB12345678
    r"^[A-Z]\d{8}$",                 # D06440929
    r"^[A-Z]{2}/\d{7}$",             # XG/0739631
    r"^[A-Z]{2}/\d+/\d+/\d{6,8}$",   # UP/20/103/774893
    r"^\d{9,10}$",                   # pure-digit EPICs
)


def _epic_ok(s: str) -> bool:
    return any(re.match(p, s) for p in _EPIC_PATTERNS)


#: Canonical Devanagari name -> accepted spellings (Latin and Devanagari
#: variants) for every State and Union Territory. A state value that matches
#: nothing here is a genuine check FAILURE, not merely unverifiable.
_STATES = {
    "आंध्र प्रदेश": ("ANDHRA PRADESH", "AP"),
    "अरुणाचल प्रदेश": ("ARUNACHAL PRADESH",),
    "असम": ("ASSAM",),
    "बिहार": ("BIHAR", "BR"),
    "छत्तीसगढ़": ("CHHATTISGARH", "CG", "छत्तीसगढ"),
    "गोवा": ("GOA",),
    "गुजरात": ("GUJARAT", "GJ"),
    "हरियाणा": ("HARYANA", "HR"),
    "हिमाचल प्रदेश": ("HIMACHAL PRADESH", "HP"),
    "झारखंड": ("JHARKHAND", "JH"),
    "कर्नाटक": ("KARNATAKA", "KA"),
    "केरल": ("KERALA", "KL"),
    "मध्य प्रदेश": ("MADHYA PRADESH", "MP"),
    "महाराष्ट्र": ("MAHARASHTRA", "MH"),
    "मणिपुर": ("MANIPUR",),
    "मेघालय": ("MEGHALAYA",),
    "मिजोरम": ("MIZORAM",),
    "नागालैंड": ("NAGALAND",),
    "ओडिशा": ("ODISHA", "ORISSA", "OD", "उडीसा"),
    "पंजाब": ("PUNJAB", "PB"),
    "राजस्थान": ("RAJASTHAN", "RJ"),
    "सिक्किम": ("SIKKIM",),
    "तमिलनाडु": ("TAMIL NADU", "TN"),
    "तेलंगाना": ("TELANGANA", "TS", "TG"),
    "त्रिपुरा": ("TRIPURA",),
    "उत्तर प्रदेश": ("UTTAR PRADESH", "UP", "U.P.", "U.P"),
    "उत्तराखंड": ("UTTARAKHAND", "UK", "UTTARANCHAL"),
    "पश्चिम बंगाल": ("WEST BENGAL", "WB"),
    # Union Territories
    "अंडमान और निकोबार द्वीपसमूह": ("ANDAMAN AND NICOBAR ISLANDS", "ANDAMAN & NICOBAR ISLANDS"),
    "चंडीगढ़": ("CHANDIGARH", "चंडीगढ"),
    "दादरा और नगर हवेली तथा दमन और दीव": ("DADRA AND NAGAR HAVELI AND DAMAN AND DIU",),
    "दिल्ली": ("DELHI", "NCT OF DELHI", "NEW DELHI", "नई दिल्ली"),
    "जम्मू और कश्मीर": ("JAMMU AND KASHMIR", "JAMMU & KASHMIR", "J&K"),
    "लद्दाख": ("LADAKH",),
    "लक्षद्वीप": ("LAKSHADWEEP",),
    "पुडुचेरी": ("PUDUCHERRY", "PONDICHERRY"),
}

#: lookup key (upper-cased, punctuation-trimmed) -> canonical Devanagari name
_STATE_LOOKUP = {}
for _canon, _aliases in _STATES.items():
    _STATE_LOOKUP[_canon.upper()] = _canon
    for _a in _aliases:
        _STATE_LOOKUP[_a.upper()] = _canon


# ---------------------------------------------------------------------------
# Validators — one per `kind`. Each returns (value, status, note).
# A failing validator NEVER returns None for a non-empty raw: it hands the raw
# value back marked needs_review so the operator can see and correct it.
# ---------------------------------------------------------------------------

_NO_CHECK = "free text — no automatic check possible, confirm against the image"


def _v_text(raw):
    v = _clean_text(raw)
    return (v, UNVERIFIED, _NO_CHECK) if v else (None, MISSING, None)


def _v_name(raw):
    v = _clean_text(raw)
    if not v:
        return None, MISSING, None
    if len(v) > 60 or len(v.split()) > 6:
        return v, NEEDS_REVIEW, "unusually long for a name — possible OCR bleed from an adjacent row"
    return v, UNVERIFIED, _NO_CHECK


def _v_address(raw):
    v = _clean_text(raw)
    if not v:
        return None, MISSING, None
    if len(v) < 6:
        return v, NEEDS_REVIEW, "address looks truncated"
    return v, UNVERIFIED, _NO_CHECK


def _v_integer(raw):
    v = _clean_text(raw)
    if not v:
        return None, MISSING, None
    d = _digits(v)
    if not d:
        return v, NEEDS_REVIEW, "expected a number"
    return d, VERIFIED, None


def _v_digits10(raw):
    """Indian mobile: 10 digits starting 6-9, +91/91/0 prefixes stripped."""
    v = _clean_text(raw)
    if not v:
        return None, MISSING, None
    d = _digits(v)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10 and d[0] in "6789":
        return d, VERIFIED, None
    if len(d) < 10:
        return v, NEEDS_REVIEW, f"only {len(d)} digits read — number is truncated or partly out of frame"
    if len(d) > 10:
        return v, NEEDS_REVIEW, f"{len(d)} digits read — likely merged with an adjacent row (e.g. Aadhaar)"
    return v, NEEDS_REVIEW, "10 digits but does not start with 6-9"


def _v_aadhaar(raw):
    v = _clean_text(raw)
    if not v:
        return None, MISSING, None
    d = _digits(v)
    if len(d) != 12:
        return v, NEEDS_REVIEW, f"{len(d)} digits read — Aadhaar must be 12"
    if not _verhoeff_ok(d):
        return d, NEEDS_REVIEW, "12 digits but checksum fails — at least one digit is misread"
    return d, VERIFIED, None


def _v_epic(raw):
    v = _clean_text(raw)
    if not v:
        return None, MISSING, None
    s = re.sub(r"\s+", "", v).upper().replace(".", "/").rstrip("/.-")
    if _epic_ok(s):
        return s, VERIFIED, None
    return s, NEEDS_REVIEW, "does not match a known EPIC format"


def _v_state(raw):
    v = _clean_text(raw)
    if not v:
        return None, MISSING, None
    key = re.sub(r"\s+", " ", v.upper()).strip().strip(".")
    if key in _STATE_LOOKUP:
        return _STATE_LOOKUP[key], VERIFIED, None
    return v, NEEDS_REVIEW, "not a recognised State or Union Territory name"


_VALIDATORS = {
    "text": _v_text, "name": _v_name, "address": _v_address,
    "integer": _v_integer, "digits10": _v_digits10, "aadhaar": _v_aadhaar,
    "epic": _v_epic, "state": _v_state,
}


def validate(key: str, raw, source: str = "model") -> dict:
    """Normalise + validate one field by its schema `kind`, returning an envelope."""
    spec = BY_KEY.get(key)
    validator = _VALIDATORS.get(spec.kind if spec else "text", _v_text)
    value, status, note = validator(raw)
    return field(value, raw=raw, source=source, status=status, note=note)


# ---------------------------------------------------------------------------
# Split helper — part number and part name arrive merged from the model
# ---------------------------------------------------------------------------

def split_part(merged: str | None) -> tuple[str | None, str | None]:
    """'111 लखनऊ क्रिस्चियन कॉलेज' → ('111', 'लखनऊ क्रिस्चियन कॉलेज')."""
    v = _clean_text(merged)
    if not v:
        return None, None
    m = re.match(r"^(\d{1,5})\s*[-–—.:]?\s*(.*)$", v)
    if not m:
        return None, v
    return m.group(1), (m.group(2).strip() or None)
