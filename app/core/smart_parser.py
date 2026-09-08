"""
HTML-aware voter card OCR parser.

Built from analysis of 43 real ChandraOCR outputs for Indian EPIC (voter) cards
(गणना प्रपत्र). Handles two structural patterns:

  Pattern A (HTML table):
    Left <td>:   voter name, EPIC, address (newline-separated, often with <br/>)
    Right <td>:  serial#, part# + name, constituency, state
    Later tables: DOB, Aadhaar, mobile, father/mother/spouse names

  Pattern B (plain text):
    Primary data appears as "label: value\\n" lines BEFORE any <table> tag.
    Later tables still contain supplemental data.

Output shape:
  {"name": {"value": "...", "confidence": 0.95}, ...}
"""

import re
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# OCR variant keyword sets (updated for ChandraOCR corruption patterns)
# ---------------------------------------------------------------------------

# निर्वाचक is commonly corrupted to निरीचक / निवासक / निवाँधक
_NAME_KEYWORDS = (
    "निर्वाचक का नाम",
    "निरीचक का नाम",
    "निवासक का नाम",
    "निवाँधक का नाम",
    "परिवार का नाम",    # extreme OCR corruption seen in field
)

# क्रम संख्या corruptions: क्रम→कण, कम, कंप, डम, डमरू, ब्लॉक, ग्राम
_SERIAL_PREFIX = r"(?:क्रम|कम|कंप|कण|डम(?:रु)?|ब्लॉक|ग्राम)"

# भाग संख्या एवं नाम: unique trigger is "संख्या एवं"
# (covered inline via `"संख्या एवं" in cell`)

# विधानसभा / संसदीय निर्वाचन क्षेत्र: anchors are "विधानसभा" / "निधानसभा" / "क्षेत्र का"
# (covered inline)


# ---------------------------------------------------------------------------
# HTML → cell list
# ---------------------------------------------------------------------------

class _CellExtractor(HTMLParser):
    """Walks the HTML and collects each <td> and <th> as a string, with <br/> → \\n."""

    _CELL_TAGS = {"td", "th"}

    def __init__(self):
        super().__init__()
        self.cells: list[str] = []
        self._buf: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in self._CELL_TAGS:
            self._buf = []
        elif tag == "br" and self._buf is not None:
            self._buf.append("\n")
        # <b> and <del> are pass-through: data is captured by handle_data()

    def handle_endtag(self, tag):
        if tag in self._CELL_TAGS and self._buf is not None:
            self.cells.append("".join(self._buf))
            self._buf = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)


def _cells(html: str) -> list[str]:
    p = _CellExtractor()
    p.feed(html)
    # Normalize indentation inside cells: \n + spaces → \n so lookaheads work
    return [re.sub(r"\n[ \t]+", "\n", cell).strip() for cell in p.cells]


# ---------------------------------------------------------------------------
# EPIC validation
# ---------------------------------------------------------------------------

_EPIC_PATTERNS = [
    r"^[A-Z]{3}\d{7}$",             # XGF2057644
    r"^[A-Z]{2}\d{8}$",             # AB12345678
    r"^[A-Z]\d{8}$",                # D06440929
    r"^[A-Z]{2}/\d{7}$",            # XG/0739631
    r"^[A-Z]{2}/\d+/\d+/\d{6,8}$", # UP/20/102/0732650
    r"^\d{9,10}$",                  # 1002345429, 0034109129 (pure-digit EPICs)
]


def _valid_epic(s: str) -> bool:
    return any(re.match(p, s) for p in _EPIC_PATTERNS)


def _normalise_epic(raw: str) -> str | None:
    """Strip spaces, normalise OCR period-for-slash, validate."""
    s = re.sub(r"\s+", "", raw).upper()
    s = s.replace(".", "/")
    s = s.rstrip("/.-")
    return s if _valid_epic(s) else None


def _strip_markdown(v: str) -> str:
    """Remove common markdown formatting artifacts (*bold*, **bold**, etc.)."""
    v = re.sub(r"\*+", "", v)
    v = re.sub(r"~~[^~]*~~", "", v)
    v = re.sub(r"`[^`]*`", "", v)
    return v.strip()


# ---------------------------------------------------------------------------
# Field extractors — header-cell (multi-field, \\n-separated)
# ---------------------------------------------------------------------------

def _name_from_cell(cell: str) -> str | None:
    """
    Voter name label with OCR corruption variants:
    निर्वाचक / निरीचक / निवासक / निवाँधक का नाम
    """
    m = re.search(
        r"(?:निर्वाचक|निरीचक|निवासक|निवाँधक|परिवार)\s*का\s*नाम\s*:\s*([^:\n][^\n]*)",
        cell,
    )
    if not m:
        return None
    v = re.sub(r"\s+", " ", m.group(1)).strip("* \t")
    v = _strip_markdown(v)
    if not v or v == ":":
        return None
    # Guard: if the value looks like a sentence (>4 words) it's OCR bleed
    words = v.split()
    return " ".join(words[:4]) if len(words) > 4 else v


def _epic_from_cell(cell: str) -> str | None:
    """
    Only matches the voter's own EPIC label (ईपीआईसी:).
    Skips cells that contain 'यदि उपलब्ध हो' (relative EPIC fields).

    Labelled values are trusted even when format validation fails (e.g. OCR
    reads letters as digits: 'OO84713903' → '0084713903').
    Bare token scan uses strict format validation.

    Handles spaced EPICs: MCG 0982678, HJ N2044502, XGF 1797 140.
    """
    if "यदि उपलब्ध हो" in cell:
        return None

    # Labelled match — trust the label; apply only light cleanup (no format gate)
    m = re.search(r"ईपीआईसी\s*:\s*([A-Z0-9][A-Z0-9/\.\- ]+)", cell, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        raw = re.sub(r"\s+", "", raw).upper().replace(".", "/").rstrip("/.-")
        if len(raw) >= 6:
            return raw

    # Bare token scan — strict format validation
    for token in re.findall(r"\b([A-Z]{1,3}[0-9/\.]{6,}[0-9])\b", cell):
        result = _normalise_epic(token)
        if result:
            return result

    return None


def _address_from_cell(cell: str) -> str | None:
    """
    Address starts after पता: and runs until the next field label or end of cell.
    Lookahead covers serial/part/constituency/state labels and their corruptions.
    """
    m = re.search(
        r"पता\s*:\s*(.+?)"
        r"(?=\n(?:"
        r"(?:निर्वाचक|निरीचक|निवासक|निवाँधक)\s*का\s*नाम"
        r"|ईपीआईसी"
        r"|(?:क्रम|कम|कंप|कण|डम|ब्लॉक|ग्राम)\s*संख्या"
        r"|(?:भाग|पान|माप|चयन|ग्राम|वाम|नाम|माग|पाग|मांग|नाग|ब्लॉक)\s*संख्या"
        r"|क्षेत्र\s*का"
        r"|(?:राज्य|ज्या)\s*का"
        r")|$)",
        cell, re.DOTALL,
    )
    if not m:
        return None
    v = re.sub(r"\n+", " ", m.group(1))
    v = re.sub(r"\s+", " ", v).strip("* \t")
    v = _strip_markdown(v)
    return v if len(v) > 5 else None


def _serial_from_cell(cell: str) -> str | None:
    """
    क्रम संख्या and all OCR corruption variants:
    क्रम, कम, कंप, कण, डम, डमरू, ब्लॉक, ग्राम
    """
    m = re.search(_SERIAL_PREFIX + r"\s*संख्या\s*:?\s*(\d+)", cell)
    return m.group(1) if m else None


def _part_from_cell(cell: str) -> str | None:
    """
    भाग संख्या एवं नाम (and OCR corruption variants for भाग prefix and नाम suffix).
    Trigger condition: cell contains 'संख्या एवं' (unique to this field).
    Prefix variants: भाग, पान, माप, चयन, ग्राम, वाम, नाम, माग, पाग, मांग, नाग, ब्लॉक
    Suffix variants: नाम, भाग, गान
    Value runs until the next field label or end of cell.
    """
    m = re.search(
        r"(?:भाग|पान|माप|चयन|ग्राम|वाम|नाम|माग|पाग|मांग|नाग|ब्लॉक)"
        r"\s*संख्या\s+(?:एवं\s+(?:नाम|भाग|गान)\s*)?:?\s*"
        r"(.+?)"
        r"(?=\n(?:क्षेत्र\s*का|(?:राज्य|ज्या)\s*का|(?:क्रम|कम|कंप|कण|डम|ब्लॉक|ग्राम)\s*संख्या|(?:विधान\s*सभा|निधान\s*सभा|संसदीय))|$)",
        cell, re.DOTALL,
    )
    if not m:
        # Fallback: old-style भाग संख्या without एवं (e.g. "भाग संख्या: 123 मध्य")
        m = re.search(
            r"भाग\s*संख्या\s*:?\s*(.+?)"
            r"(?=\n(?:क्षेत्र\s*का|(?:राज्य|ज्या)\s*का|(?:क्रम|कम|कंप|कण|डम|ब्लॉक|ग्राम)\s*संख्या)|$)",
            cell, re.DOTALL,
        )
    if not m:
        return None
    v = re.sub(r"\n+", " ", m.group(1))
    v = re.sub(r"\s+", " ", v).strip("* \t")
    v = _strip_markdown(v)
    return v if v else None


def _constituency_from_cell(cell: str) -> str | None:
    """
    विधानसभा / संसदीय निर्वाचन क्षेत्र का नाम.
    Trigger condition: cell contains 'विधानसभा' / 'निधानसभा' / 'क्षेत्र का'.
    Handles two label forms:
      - 'विधानसभा ... का नाम:' (e.g. 'विधानसभा / सरकारी निरीचन डीए का नाम:')
      - 'क्षेत्र का नाम:' / 'क्षेत्र का माग:'
    Constituency value often spans two lines: 'लखनऊ\\nमध्य' → 'लखनऊ मध्य'.
    """
    m = re.search(
        r"(?:(?:विधान\s*सभा|निधान\s*सभा)[^:\n]*का\s*(?:नाम|माग)|क्षेत्र\s*का\s*(?:नाम|माग))"
        r"\s*:?\s*(.+?)(?=\n(?:राज्य|ज्या)|$)",
        cell, re.DOTALL,
    )
    if not m:
        return None
    v = re.sub(r"\n+", " ", m.group(1))
    v = re.sub(r"\s+", " ", v).strip("* \t")
    v = _strip_markdown(v)
    return v if v else None


def _state_from_cell(cell: str) -> str | None:
    """
    राज्य का नाम (and OCR corruption ज्या का नाम).
    """
    m = re.search(r"(?:राज्य|ज्या)\s*का\s*नाम\s*:?\s*([^\n<]+)", cell)
    if not m:
        # Fallback: shorter form राज्य:
        m = re.search(r"(?:राज्य|ज्या)\s*:?\s*([^\n<]+)", cell)
    if not m:
        return None
    return _normalise_state(m.group(1).strip())


def _normalise_state(v: str) -> str | None:
    abbrevs = {"UP", "U.P.", "U.P", "उ0. पु0", "उ0.पु0", "UTTAR PRADESH"}
    if v.upper().strip().rstrip(".") in {a.upper().rstrip(".") for a in abbrevs}:
        return "उत्तर प्रदेश"
    cleaned = re.sub(r"[^ऀ-ॿA-Za-z\s]", "", v).strip()
    return cleaned if cleaned else None


# ---------------------------------------------------------------------------
# Field extractors — label→value adjacent cell pairs
# ---------------------------------------------------------------------------

def _mobile_from_pair(label: str, value: str) -> str | None:
    """
    Mobile number label: मोबाइल नंबर and OCR corruptions पीडाइल / पीडाइत नंबर.
    Handles +91 / 91 country-code prefix (strips it before returning).
    """
    if not re.search(r"(?:मोबाइल|पीडाइल|पीडाइत)\s*नंबर", label):
        return None
    digits_only = re.sub(r"\s+", "", value)
    # Country-code prefix: +91XXXXXXXXXX or 91XXXXXXXXXX → strip 91, return 10 digits
    m = re.match(r"^\+?91([6-9]\d{9})$", digits_only)
    if m:
        return m.group(1)
    # Clean 10-digit number (direct or with OCR-inserted spaces)
    m = re.search(r"\b([6-9]\d{9})\b", value)
    if m:
        return m.group(1)
    m = re.search(r"([6-9]\d{9})", digits_only)
    if m and len(digits_only) == 10:
        return m.group(1)
    return None


def _strip_district_prefix(v: str) -> str:
    """Remove 'जिला:', 'जिला :', 'जिला' prefix that OCR sometimes includes in the value."""
    return re.sub(r"^जिल[ाेोां]*\s*[:]?\s*", "", v).strip()


def _district_from_pair(label: str, value: str) -> str | None:
    if re.search(r"^जिल", label.strip()):
        v = _strip_district_prefix(value.strip())
        return v if v and v not in ("—", "-", "-", "") else None
    # Also catch when label+value are merged in a single cell: "जिला: लखनऊ"
    m = re.search(r"^जिल[ाेोां]*\s*[:]\s*(.+)", label.strip())
    if m:
        v = _strip_district_prefix(m.group(1).strip())
        return v if v and v not in ("—", "-", "-", "") else None
    return None


def _state_from_pair(label: str, value: str) -> str | None:
    if re.search(r"(?:राज्य|ज्या)\s*(?:का\s*नाम)?", label):
        v = value.strip()
        return _normalise_state(v) if v and v not in ("—", "-") else None
    return None


# ---------------------------------------------------------------------------
# Plain-text fallback pass (Pattern B — pre-table content)
# ---------------------------------------------------------------------------

def _strip_html_tags(text: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _plain_text_section(raw: str) -> str:
    """
    Extract the portion of raw text BEFORE the first <table> tag.
    If no table is present, return the full text (strip HTML tags).
    Normalises Markdown artifacts so field regexes work cleanly:
      - Strips HTML tags
      - Strips ** bold markers
      - Strips Markdown images ![alt](url) — prevents them bleeding into field values
      - Normalises \n + leading whitespace → \n (same as _cells() for HTML)
    """
    idx = raw.find("<table")
    section = raw[:idx] if idx != -1 else raw
    text = _strip_html_tags(section)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", "", text)  # strip Markdown images
    text = re.sub(r"\n[ \t]+", "\n", text)              # normalise indented lines
    return text


def _extract_plain_fields(text: str) -> dict:
    """
    Apply regex extraction to plain-text section for all 9 fields.
    Returns a dict with non-None values only.
    """
    found: dict = {}

    # name
    m = re.search(
        r"(?:निर्वाचक|निरीचक|निवासक|निवाँधक|परिवार)\s*का\s*नाम\s*:?\s*([^\n:]+)",
        text,
    )
    if m:
        v = re.sub(r"\s+", " ", m.group(1)).strip("* \t")
        v = _strip_markdown(v)
        if v:
            words = v.split()
            found["name"] = " ".join(words[:4]) if len(words) > 4 else v

    # EPIC (labelled)
    m = re.search(
        r"ईपीआईसी\s*:?\s*([A-Z0-9][A-Z0-9/\.\- ]{4,})",
        text, re.IGNORECASE,
    )
    if m and "यदि उपलब्ध हो" not in text[max(0, m.start() - 30): m.start()]:
        raw = re.sub(r"\s+", "", m.group(1)).upper().replace(".", "/").rstrip("/.-")
        if len(raw) >= 6:
            found["epic"] = raw

    # address
    serial_lookahead = (
        r"(?:क्रम|कम|कंप|कण|डम|ब्लॉक|ग्राम)\s*संख्या"
        r"|(?:भाग|पान|माप|चयन|ग्राम|वाम|नाम|माग|पाग|मांग|नाग|ब्लॉक)\s*संख्या"
        r"|(?:विधान|निर्वाचन)"
        r"|(?:राज्य|ज्या)"
        r"|ईपीआईसी"
        r"|(?:मोबाइल|पीडाइल|पीडाइत)\s*नंबर"
        r"|जन्म"
    )
    m = re.search(
        r"पता\s*:\s*(.+?)(?=\n(?:" + serial_lookahead + r")|$)",
        text, re.DOTALL,
    )
    if m:
        v = re.sub(r"\n+", " ", m.group(1))
        v = re.sub(r"\s+", " ", v).strip("* \t")
        v = _strip_markdown(v)
        if len(v) > 5:
            found["address"] = v

    # serial_number
    m = re.search(_SERIAL_PREFIX + r"\s*संख्या\s*:?\s*(\d+)", text)
    if m:
        found["serial_number"] = m.group(1)

    # part_number_and_name
    m = re.search(
        r"(?:भाग|पान|माप|चयन|ग्राम|वाम|नाम|माग|पाग|मांग|नाग|ब्लॉक)"
        r"\s*संख्या\s+(?:एवं\s+(?:नाम|भाग|गान)\s*)?:?\s*(.+?)"
        r"(?=\n(?:विधान|निर्वाचन|राज्य|ज्या|जन्म|आधार|(?:मोबाइल|पीडाइल|पीडाइत)\s*नंबर)|$)",
        text, re.DOTALL,
    )
    if m:
        v = re.sub(r"\n+", " ", m.group(1))
        v = re.sub(r"\s+", " ", v).strip("* \t")
        v = _strip_markdown(v)
        if v:
            found["part_number_and_name"] = v

    # assembly_constituency
    m = re.search(
        r"(?:(?:विधान\s*सभा|निधान\s*सभा)[^:\n]*का\s*(?:नाम|माग)|क्षेत्र\s*का\s*(?:नाम|माग))"
        r"\s*:?\s*(.+?)(?=\n(?:राज्य|ज्या)|$)",
        text, re.DOTALL,
    )
    if m:
        v = re.sub(r"\n+", " ", m.group(1))
        v = re.sub(r"\s+", " ", v).strip("* \t")
        v = _strip_markdown(v)
        if v:
            found["assembly_constituency"] = v

    # state
    m = re.search(r"(?:राज्य|ज्या)\s*का\s*नाम\s*:?\s*([^\n]+)", text)
    if m:
        v = _normalise_state(m.group(1).strip())
        if v:
            found["state"] = v

    # mobile
    m = re.search(
        r"(?:मोबाइल|पीडाइल|पीडाइत)\s*नंबर\s*[:\-—]?\s*(?:\n[\s\n]*)?"
        r"([6-9][\d ]{9,12})",
        text,
    )
    if m:
        raw = re.sub(r"\s+", "", m.group(1))
        if len(raw) == 10:
            found["mobile"] = raw

    return found


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _score(value, *, format_valid=False, label_match=False, clean=False, db_match=False) -> float:
    if not value:
        return 0.0
    s = 0.4
    if format_valid: s += 0.2
    if label_match:  s += 0.2
    if clean:        s += 0.15
    if db_match:     s += 0.15
    return round(min(s, 0.99), 2)


def _fmt(value, confidence: float) -> dict:
    return {"value": value or None, "confidence": round(confidence, 2) if value else 0.0}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_smart(raw_html: str) -> dict:
    """
    Parse raw ChandraOCR output (HTML+Markdown) into structured voter-card fields.

    Handles both structural patterns:
      Pattern A: primary data in HTML table cells
      Pattern B: primary data as plain "label: value" lines before any <table>

    Returns a dict with the same shape as the Claude parser output:
      {"name": {"value": "...", "confidence": 0.95}, ...}
    """
    fields = {
        "name": None, "epic": None, "mobile": None,
        "serial_number": None, "part_number_and_name": None,
        "assembly_constituency": None, "district": None,
        "state": None, "address": None,
    }

    try:
        cells = _cells(raw_html)
    except Exception as e:
        print(f"[smart_parser] HTML parse error: {e}")
        cells = []

    # ── Pass 1: plain-text pre-table section ──────────────────────────────
    # Must run FIRST so Pattern B voter fields (name/EPIC/address/serial/…)
    # are not overwritten by later-table cells that reuse the same labels
    # (e.g. "पिछले SIR" section repeats निर्वाचक का नाम with the BLO's name).
    # For Pattern A documents the pre-table section is just headers; the
    # extractor finds nothing and the HTML passes below handle everything.
    plain = _plain_text_section(raw_html)
    plain_found = _extract_plain_fields(plain)
    for key, val in plain_found.items():
        fields[key] = val

    # ── Pass 2: header cells (multi-field, \\n-delimited) ─────────────────
    for cell in cells:
        # Name cell: contains voter name label
        if any(kw in cell for kw in _NAME_KEYWORDS):
            fields["name"]    = fields["name"]    or _name_from_cell(cell)
            fields["epic"]    = fields["epic"]    or _epic_from_cell(cell)
            fields["address"] = fields["address"] or _address_from_cell(cell)

        # Serial number cell
        if re.search(_SERIAL_PREFIX + r"\s*संख्या", cell):
            fields["serial_number"] = fields["serial_number"] or _serial_from_cell(cell)

        # Part number + name cell (unique trigger: "संख्या एवं")
        if "संख्या एवं" in cell:
            fields["part_number_and_name"] = (
                fields["part_number_and_name"] or _part_from_cell(cell)
            )

        # Constituency cell — label is either "विधानसभा ... का नाम" or "क्षेत्र का नाम"
        if "विधान" in cell or "निधान" in cell or "क्षेत्र का" in cell:
            fields["assembly_constituency"] = (
                fields["assembly_constituency"] or _constituency_from_cell(cell)
            )

        # State cell (राज्य or OCR corruption ज्या)
        if "राज्य" in cell or "ज्या" in cell:
            fields["state"] = fields["state"] or _state_from_cell(cell)

    # ── Pass 3: adjacent label→value cell pairs ────────────────────────────
    for i in range(len(cells) - 1):
        label, value = cells[i], cells[i + 1]

        if fields["mobile"] is None:
            fields["mobile"] = _mobile_from_pair(label, value)

        if fields["district"] is None:
            fields["district"] = _district_from_pair(label, value)

        if fields["state"] is None:
            fields["state"] = _state_from_pair(label, value)

    # ── Build output ───────────────────────────────────────────────────────
    epic   = fields["epic"]
    name   = fields["name"]
    mobile = fields["mobile"]

    return {
        "name": _fmt(name, _score(
            name,
            label_match=True,
            clean=bool(name and len(name.split()) <= 4),
        )),
        "epic": _fmt(epic, _score(
            epic,
            format_valid=_valid_epic(epic or ""),
            label_match=True,
        )),
        "mobile": _fmt(mobile, _score(
            mobile,
            format_valid=bool(mobile and len(mobile) == 10 and mobile[0] in "6789"),
            label_match=True,
        )),
        "serial_number": _fmt(
            fields["serial_number"],
            0.97 if fields["serial_number"] else 0.0,
        ),
        "part_number_and_name": _fmt(
            fields["part_number_and_name"],
            _score(fields["part_number_and_name"], label_match=True, clean=True),
        ),
        "assembly_constituency": _fmt(
            fields["assembly_constituency"],
            _score(fields["assembly_constituency"], label_match=True),
        ),
        "district": _fmt(
            fields["district"],
            _score(fields["district"], label_match=True, clean=True),
        ),
        "state": _fmt(
            fields["state"],
            0.99 if fields["state"] == "उत्तर प्रदेश" else _score(fields["state"], label_match=True),
        ),
        "address": _fmt(
            fields["address"],
            _score(
                fields["address"],
                label_match=True,
                clean=bool(fields["address"] and len(fields["address"]) > 20),
            ),
        ),
    }
