"""
The single source of truth for what a गणना प्रपत्र (enumeration form) contains.

Every stage of the pipeline speaks this field set:
  - the OCR prompt is GENERATED from it (build_prompt), so the model and the
    backend can no longer drift apart,
  - the field mapping in the workers reads MODEL_KEY off it,
  - field_validation.py validates each field by its `kind`.

Adding a field is a single edit here — not a prompt edit plus a mapping edit
plus a regex.

The JSON keys of the pre-existing Colab prompt (voter_name, epic_number,
address, serial_number, part_number_name, constituency, state, mobile_number)
are kept verbatim so an un-updated Colab endpoint keeps working. Everything
added since is optional and simply arrives as None until the notebook is
regenerated from build_prompt().
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    key: str           # canonical name used in job.result["parsed"]
    model_key: str     # key expected back from the OCR model
    kind: str          # drives validation: text|name|epic|digits10|integer|state|address
    label_hi: str      # the printed label on the form, for the prompt
    required: bool = False
    ask: bool = True   # False = never requested from the model; filled from the DB


#: EXACTLY the eight keys the app saves, plus `district`, which is never
#: requested from the model — it is derived from the constituency reference
#: table by apply_constituency_resolution() and is null until that matches.
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name",                 "voter_name",       "name",     "निर्वाचक का नाम", required=True),
    FieldSpec("epic",                 "epic_number",      "epic",     "ईपीआईसी संख्या", required=True),
    FieldSpec("address",              "address",          "address",  "पता"),
    FieldSpec("serial_number",        "serial_number",    "integer",  "क्रम संख्या"),
    FieldSpec("part_number_and_name", "part_number_name", "text",     "भाग संख्या एवं नाम"),
    FieldSpec("assembly_constituency","constituency",     "text",     "विधानसभा निर्वाचन क्षेत्र का नाम"),
    FieldSpec("state",                "state",            "state",    "राज्य का नाम"),
    FieldSpec("mobile",               "mobile_number",    "digits10", "मोबाइल नंबर"),

    # Not asked of the model — resolved from the reference table.
    FieldSpec("district",             "district",         "text",     "जिला", ask=False),
)

BY_KEY = {f.key: f for f in FIELDS}
BY_MODEL_KEY = {f.model_key: f for f in FIELDS}

#: The exact key order in job.result["parsed"]. This IS the full field set
#: now, not a legacy subset — nothing else is produced.
LEGACY_KEYS = (
    "name", "epic", "mobile", "serial_number", "part_number_and_name",
    "assembly_constituency", "district", "state", "address",
)


_KIND_HINT = {
    "digits10": "exactly 10 digits, no country code, no spaces",
    "integer":  "digits only",
    "epic":     "as printed, e.g. XGF0739839 or UP/20/103/774893",
    "state":    "full state name in Devanagari",
    "name":     "as written, Devanagari or Latin, no honorific expansion",
    "address":  "the full address on one line, commas preserved",
    "text":     "as printed",
}


def build_prompt() -> str:
    """
    Generate the OCR extraction prompt from FIELDS.

    Paste the output of this function into the Colab notebook so the notebook's
    prompt and this repo cannot diverge. It is also sent with each request as
    the optional `prompt` form field — an endpoint that ignores it is unaffected.
    """
    lines = [
        "You are reading a scanned Indian Election Commission enumeration form "
        "(गणना प्रपत्र). The form is bilingual (Hindi/English) and mixes printed "
        "labels with handwritten answers.",
        "",
        "Read the WHOLE page. Answers sit in the right-hand column of each row; "
        "match every answer to the label on its own row and never carry a value "
        "up or down into a neighbouring row.",
        "",
        "Return ONE JSON object and nothing else. Use these exact keys:",
        "",
    ]
    for f in FIELDS:
        if not f.ask:
            continue
        hint = _KIND_HINT.get(f.kind, "as printed")
        lines.append(f'  "{f.model_key}"  — {f.label_hi} — {hint}')
    lines += [
        "",
        "Rules:",
        "  - If a field is absent, illegible, or blank on the form, use null. "
        "Never guess and never copy a value from another row.",
        "  - Transcribe digits exactly as written. Do not pad, truncate, "
        "reformat, or complete a partially visible number.",
        "  - Keep Devanagari text in Devanagari. Do not transliterate or translate.",
        "  - Output raw JSON with no markdown fence and no commentary.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(build_prompt())
