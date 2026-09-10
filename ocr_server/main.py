# ============================================================
# PRAMAAN / ECI QWEN-VL OCR SERVICE
# Qwen2.5-VL-7B-Instruct + FastAPI
#
# Production extraction of the Colab notebook
# (ECI_OCR_Backend_MODEL_ARYAN.ipynb).
#
# OCR behaviour and the API contract are preserved verbatim:
# prompts, blur threshold, preprocessing, two-stage inference,
# validation, retry, scoring and the response shape are unchanged.
#
# Removed from the notebook (Colab-only): nest_asyncio, pyngrok,
# tunnel creation, the hardcoded ngrok token, public-URL printing
# and the top-level `await server.serve()`.
#
# Run with:  uvicorn main:app --host 0.0.0.0 --port 8000
# ============================================================


# ============================================================
# STEP 1 : IMPORTS
# ============================================================

import hmac
import io
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Optional

import cv2
import numpy as np
import torch
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from PIL import Image, ImageEnhance
from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor,
)

from qwen_vl_utils import process_vision_info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("pramaan-ocr")


# ============================================================
# STEP 2 : CONFIGURATION
# ============================================================

MODEL_NAME = "Qwen/Qwen2.5-VL-7B-Instruct"

REQUIRED_FIELDS = [
    "voter_name",
    "epic_number",
    "address",
    "serial_number",
    "part_number_name",
    "constituency",
    "state",
    "mobile_number",
]

# Blur threshold.
# This may need adjustment after testing with your actual ECI images.
BLUR_THRESHOLD = 100

# ============================================================
# STEP 3 : SHARED-SECRET AUTHENTICATION
# ============================================================

# Set OCR_SHARED_SECRET in the environment to require callers to
# authenticate. While it is unset, authentication is DISABLED and the
# service behaves exactly like the notebook — this keeps the existing
# backend working unchanged until the client is wired up separately.
#
# Accepted forms, once enabled:
#   X-API-Key: <secret>
#   Authorization: Bearer <secret>
#
# The value is never logged or returned in any response.

OCR_SHARED_SECRET = os.getenv("OCR_SHARED_SECRET", "").strip()


async def verify_shared_secret(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """Reject unauthenticated callers when a shared secret is configured."""

    if not OCR_SHARED_SECRET:
        return

    presented = x_api_key

    if not presented and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            presented = token.strip()

    if not presented or not hmac.compare_digest(presented, OCR_SHARED_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing OCR credentials",
        )


# ============================================================
# STEP 4 : LOAD QWEN MODEL
# ============================================================

model = None
processor = None


def load_model():
    """Load Qwen2.5-VL once, at process startup."""

    global model, processor

    logger.info("=" * 70)
    logger.info("Loading %s ...", MODEL_NAME)
    logger.info("=" * 70)

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    processor = AutoProcessor.from_pretrained(
        MODEL_NAME,

        # Minimum visual resolution
        min_pixels=256 * 28 * 28,

        # Higher resolution helps document OCR.
        # Increase carefully depending on Colab GPU memory.
        max_pixels=1600 * 28 * 28,
    )

    model.eval()

    logger.info("=" * 70)
    logger.info("MODEL LOADED SUCCESSFULLY")
    logger.info("=" * 70)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Replaces the notebook's straight-line execution. Uvicorn does not
    # accept traffic until this completes, so the model is always ready
    # before the first request is served.
    load_model()
    yield


# ============================================================
# STEP 5 : CREATE FASTAPI APP
# ============================================================

app = FastAPI(
    title="ECI Qwen OCR API",
    version="2.0",
    lifespan=lifespan,
)


# ============================================================
# STEP 6 : HEALTH CHECK
# ============================================================
# Intentionally unauthenticated so load balancers and container
# orchestrators can probe it.

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "model": "Qwen2.5-VL-7B-Instruct",
        "pipeline": "Two Stage OCR + Field Extraction + Validation"
    }


# ============================================================
# STEP 7 : IMAGE QUALITY / BLUR DETECTION
# ============================================================

def calculate_blur_score(image):

    """
    Higher score generally means sharper image.
    Lower score generally means more blur.
    """

    image_np = np.array(image)

    if len(image_np.shape) == 3:
        gray = cv2.cvtColor(
            image_np,
            cv2.COLOR_RGB2GRAY
        )
    else:
        gray = image_np

    blur_score = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    return float(blur_score)


# ============================================================
# STEP 9 : IMAGE PREPROCESSING
# ============================================================

def preprocess_image(image):

    """
    Conservative preprocessing.

    Important:
    We do NOT aggressively threshold or binarize because
    aggressive preprocessing can damage:
    - Hindi matras
    - thin characters
    - small numbers
    - EPIC numbers
    """

    image_np = np.array(image)

    # Convert RGB -> LAB
    lab = cv2.cvtColor(
        image_np,
        cv2.COLOR_RGB2LAB
    )

    l, a, b = cv2.split(lab)

    # Mild contrast enhancement
    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    enhanced_l = clahe.apply(l)

    enhanced_lab = cv2.merge(
        [enhanced_l, a, b]
    )

    enhanced_rgb = cv2.cvtColor(
        enhanced_lab,
        cv2.COLOR_LAB2RGB
    )

    # Mild denoising
    denoised = cv2.fastNlMeansDenoisingColored(
        enhanced_rgb,
        None,
        3,
        3,
        7,
        21
    )

    # Mild sharpening
    kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0]
    ])

    sharpened = cv2.filter2D(
        denoised,
        -1,
        kernel
    )

    processed_image = Image.fromarray(
        sharpened
    )

    return processed_image


# ============================================================
# STEP 10 : QWEN IMAGE INFERENCE FUNCTION
# ============================================================

def run_qwen_with_image(image, prompt):

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": image,
                },
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    image_inputs, video_inputs = process_vision_info(
        messages
    )

    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )

    inputs = inputs.to(model.device)

    with torch.inference_mode():

        generated_ids = model.generate(
            **inputs,

            # OCR output generally does not need 4096 tokens.
            # Keeping enough space for Electoral Roll text.
            max_new_tokens=3072,

            # More deterministic output
            do_sample=False,
        )

    generated_ids_trimmed = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(
            inputs.input_ids,
            generated_ids,
        )
    ]

    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]

    return output_text.strip()


# ============================================================
# STEP 11 : QWEN TEXT-ONLY INFERENCE FUNCTION
# ============================================================

def run_qwen_with_text(prompt):

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = processor(
        text=[text],
        padding=True,
        return_tensors="pt",
    )

    inputs = inputs.to(model.device)

    with torch.inference_mode():

        generated_ids = model.generate(
            **inputs,
            max_new_tokens=2048,
            do_sample=False,
        )

    generated_ids_trimmed = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(
            inputs.input_ids,
            generated_ids,
        )
    ]

    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]

    return output_text.strip()


# ============================================================
# STEP 12 : STAGE 1 - STRICT RAW OCR PROMPT
# ============================================================

RAW_OCR_PROMPT = """
You are a STRICT OCR text extraction engine for Election Commission
of India documents, Indian Voter ID cards, and Electoral Roll pages.

Your task is ONLY to read and reproduce the visible text from the image.

CRITICAL RULES:

1. Extract text exactly as it appears in the image.

2. DO NOT translate.

3. DO NOT transliterate.

4. DO NOT convert Hindi/Devanagari text into English.

5. DO NOT convert English text into Hindi.

6. Preserve the original script and language exactly.

7. If text is Hindi, keep it in Hindi/Devanagari.

8. If text is English, keep it in English.

9. Preserve numbers exactly as visible.

10. DO NOT guess missing characters.

11. DO NOT complete partially visible numbers or words.

12. DO NOT invent information.

13. DO NOT summarize or explain the document.

14. Read all visible relevant document text.

15. Preserve labels and their values whenever possible.

Return only the extracted OCR text.

Do not add explanations.
"""


# ============================================================
# STEP 13 : STAGE 2 - EXACT 8 FIELD EXTRACTION PROMPT
# ============================================================

def create_field_extraction_prompt(raw_ocr_text):

    return f"""
You are a STRICT structured data extraction system.

You are given OCR text extracted from an Election Commission of India
document.

Your job is to extract EXACTLY the requested 8 fields.

IMPORTANT:

You MUST use only information present in the OCR text.

DO NOT translate.

DO NOT transliterate.

DO NOT change Hindi to English.

DO NOT change English to Hindi.

Preserve the original language and script.

DO NOT guess.

DO NOT invent missing information.

If a field is not available or cannot be determined confidently,
return an empty string.

Return ONLY valid JSON.

Do not add markdown.

Do not add explanations.

Do not add extra keys.

The JSON MUST contain exactly these fields:

{{
  "voter_name": "",
  "epic_number": "",
  "address": "",
  "serial_number": "",
  "part_number_name": "",
  "constituency": "",
  "state": "",
  "mobile_number": ""
}}

FIELD DEFINITIONS:

1. voter_name:
Extract only the full name of the voter.
Do not include father name, husband name, age, gender,
serial number, or address unless they are explicitly part of
the voter name.

2. epic_number:
Extract only the EPIC Number / Voter ID Number.
Do not include any other number.

3. address:
Extract only the complete residential or postal address.
Do NOT include:
- Part Number
- Part Name
- Constituency
- State unless State is explicitly part of the address
- Serial Number
- EPIC Number
- Mobile Number

4. serial_number:
Extract only the voter serial number.
Do not confuse it with:
- EPIC Number
- Part Number
- House Number
- Mobile Number
- PIN Code

5. part_number_name:
Extract Part Number and Part Name together.
Include labels if useful.

Example format:
"Part Number: 123, Part Name: XYZ"

Do NOT include voter address.

6. constituency:
Extract only the constituency name.
Do not include unrelated address information.

7. state:
Extract only the State name.

8. mobile_number:
Extract only the mobile number if explicitly present.
Do not guess or construct a mobile number.

IMPORTANT FIELD SEPARATION RULE:

The same text must NOT be copied into unrelated fields unless
the OCR text explicitly proves that the values are identical.

For example:

Address and Part Number & Name are unrelated fields.

Do not copy the address into part_number_name.

Do not copy part_number_name into address.

RAW OCR TEXT START
------------------
{raw_ocr_text}
------------------
RAW OCR TEXT END

Return ONLY the JSON object.
"""


# ============================================================
# STEP 14 : CLEAN MODEL OUTPUT
# ============================================================

def clean_json_output(text):

    text = text.strip()

    # Remove markdown fences if model accidentally adds them
    text = re.sub(
        r"^```(?:json)?",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"```$",
        "",
        text.strip()
    )

    text = text.strip()

    # Find JSON object if extra text exists
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return text


# ============================================================
# STEP 15 : PARSE AND NORMALIZE JSON
# ============================================================

def parse_and_normalize_json(output_text):

    cleaned_text = clean_json_output(
        output_text
    )

    try:
        data = json.loads(
            cleaned_text
        )
    except Exception:
        return None

    # Force exact required fields
    normalized = {}

    for field in REQUIRED_FIELDS:

        value = data.get(
            field,
            ""
        )

        if value is None:
            value = ""

        # Convert non-string values safely
        if not isinstance(
            value,
            str
        ):
            value = str(value)

        normalized[field] = value.strip()

    return normalized


# ============================================================
# STEP 16 : VALIDATE FIELD OUTPUT
# ============================================================

def validate_fields(data):

    issues = []

    if not data:
        return False, [
            "Invalid JSON"
        ]

    # --------------------------------------------------------
    # Check exact fields
    # --------------------------------------------------------

    if set(data.keys()) != set(REQUIRED_FIELDS):

        issues.append(
            "Incorrect JSON field structure"
        )

    # --------------------------------------------------------
    # Normalize values for comparisons
    # --------------------------------------------------------

    def normalize_value(value):

        return re.sub(
            r"\s+",
            " ",
            value.strip().lower()
        )

    address = normalize_value(
        data.get("address", "")
    )

    part_number_name = normalize_value(
        data.get("part_number_name", "")
    )

    epic_number = normalize_value(
        data.get("epic_number", "")
    )

    serial_number = normalize_value(
        data.get("serial_number", "")
    )

    mobile_number = normalize_value(
        data.get("mobile_number", "")
    )

    # --------------------------------------------------------
    # Address and Part Number should not be identical
    # --------------------------------------------------------

    if (
        address
        and
        part_number_name
        and
        address == part_number_name
    ):

        issues.append(
            "Address and part_number_name are identical"
        )

    # --------------------------------------------------------
    # EPIC and Serial Number should generally not be identical
    # --------------------------------------------------------

    if (
        epic_number
        and
        serial_number
        and
        epic_number == serial_number
    ):

        issues.append(
            "EPIC number and serial number are identical"
        )

    # --------------------------------------------------------
    # EPIC number should not contain extremely long text
    # --------------------------------------------------------

    if epic_number:

        if len(epic_number) > 30:

            issues.append(
                "EPIC number is suspiciously long"
            )

    # --------------------------------------------------------
    # Serial number should not be a full sentence
    # --------------------------------------------------------

    if serial_number:

        if len(serial_number.split()) > 5:

            issues.append(
                "Serial number contains suspicious text"
            )

    # --------------------------------------------------------
    # Mobile number validation
    # --------------------------------------------------------

    if mobile_number:

        digits = re.sub(
            r"\D",
            "",
            mobile_number
        )

        if len(digits) not in [10, 11, 12, 13]:

            issues.append(
                "Mobile number has suspicious length"
            )

    # --------------------------------------------------------
    # Address should not contain obvious Part Number-only data
    # --------------------------------------------------------

    if address:

        address_lower = address.lower()

        if (
            len(address.split()) <= 4
            and
            "part" in address_lower
        ):

            issues.append(
                "Address may contain Part Number information"
            )

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    is_valid = len(issues) == 0

    return is_valid, issues


# ============================================================
# STEP 17 : RETRY FIELD EXTRACTION PROMPT
# ============================================================

def create_retry_prompt(
    raw_ocr_text,
    previous_output,
    issues
):

    issues_text = "\n".join(
        f"- {issue}"
        for issue in issues
    )

    return f"""
The previous structured extraction failed validation.

You must correct the field mapping.

IMPORTANT:

- Use ONLY the OCR text.
- Do NOT guess.
- Do NOT translate.
- Preserve Hindi and English exactly.
- Do NOT copy values between unrelated fields.
- Address and Part Number & Name must be extracted separately.
- Return ONLY valid JSON.
- Return exactly the 8 required fields.

VALIDATION ISSUES:
{issues_text}

RAW OCR TEXT:
------------------
{raw_ocr_text}
------------------

PREVIOUS OUTPUT:
------------------
{previous_output}
------------------

Required JSON:

{{
  "voter_name": "",
  "epic_number": "",
  "address": "",
  "serial_number": "",
  "part_number_name": "",
  "constituency": "",
  "state": "",
  "mobile_number": ""
}}

Correct the extraction and return ONLY JSON.
"""


# ============================================================
# STEP 18 : PROCESS ONE IMAGE
# ============================================================

def process_image_candidate(
    image,
    image_label
):

    print(f"\nProcessing image candidate: {image_label}")

    # --------------------------------------------------------
    # STAGE 1 : RAW OCR
    # --------------------------------------------------------

    print("Stage 1: Running strict raw OCR...")

    raw_ocr_text = run_qwen_with_image(
        image,
        RAW_OCR_PROMPT
    )

    # --------------------------------------------------------
    # STAGE 2 : FIELD EXTRACTION
    # --------------------------------------------------------

    print("Stage 2: Extracting 8 fields...")

    extraction_prompt = create_field_extraction_prompt(
        raw_ocr_text
    )

    field_output = run_qwen_with_text(
        extraction_prompt
    )

    parsed_data = parse_and_normalize_json(
        field_output
    )

    is_valid, issues = validate_fields(
        parsed_data
    )

    # --------------------------------------------------------
    # RETRY PARSING IF SUSPICIOUS
    # --------------------------------------------------------

    if not is_valid:

        print(
            "Validation issues detected. Retrying field extraction..."
        )

        retry_prompt = create_retry_prompt(
            raw_ocr_text=raw_ocr_text,
            previous_output=field_output,
            issues=issues
        )

        retry_output = run_qwen_with_text(
            retry_prompt
        )

        retry_data = parse_and_normalize_json(
            retry_output
        )

        retry_valid, retry_issues = validate_fields(
            retry_data
        )

        # Use retry if better/valid
        if retry_valid:

            parsed_data = retry_data
            is_valid = True
            issues = []

        elif retry_data is not None:

            parsed_data = retry_data
            issues = retry_issues

    # --------------------------------------------------------
    # Return candidate result
    # --------------------------------------------------------

    return {
        "image_label": image_label,
        "raw_ocr_text": raw_ocr_text,
        "data": parsed_data,
        "valid": is_valid,
        "issues": issues,
    }


# ============================================================
# STEP 19 : SCORE OCR RESULT
# ============================================================

def score_result(result):

    """
    Used when comparing original vs enhanced image.

    Higher score = better candidate.
    """

    if not result:
        return -1000

    score = 0

    data = result.get("data")

    if data:

        # Reward populated fields
        for field in REQUIRED_FIELDS:

            value = data.get(
                field,
                ""
            )

            if value and value.strip():

                score += 10

    # Reward valid output
    if result.get("valid"):

        score += 50

    # Penalize validation issues
    issues = result.get(
        "issues",
        []
    )

    score -= len(issues) * 10

    return score

# ============================================================
# STEP 20 : OCR ENDPOINT
# ============================================================

@app.post("/ocr")
async def run_ocr(
    file: UploadFile = File(...),
    _auth: None = Depends(verify_shared_secret),
):

    try:

        print("\n")
        print("=" * 70)
        print("OCR REQUEST RECEIVED")
        print("=" * 70)

        # ----------------------------------------------------
        # READ IMAGE
        # ----------------------------------------------------

        image_bytes = await file.read()

        original_image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        # ----------------------------------------------------
        # IMAGE QUALITY CHECK
        # ----------------------------------------------------

        blur_score = calculate_blur_score(
            original_image
        )

        is_blurry = (
            blur_score < BLUR_THRESHOLD
        )

        print(
            f"Blur Score: {blur_score:.2f}"
        )

        print(
            f"Image classified as: "
            f"{'BLURRED' if is_blurry else 'CLEAR'}"
        )

        # ----------------------------------------------------
        # CLEAR IMAGE
        # ----------------------------------------------------

        if not is_blurry:

            result = process_image_candidate(
                original_image,
                "original_clear"
            )

            final_result = result

        # ----------------------------------------------------
        # BLURRED IMAGE
        # ----------------------------------------------------

        else:

            print(
                "\nBlurred image detected."
            )

            print(
                "Processing ORIGINAL image..."
            )

            original_result = process_image_candidate(
                original_image,
                "original_blurred"
            )

            print(
                "\nCreating enhanced image..."
            )

            enhanced_image = preprocess_image(
                original_image
            )

            print(
                "Processing ENHANCED image..."
            )

            enhanced_result = process_image_candidate(
                enhanced_image,
                "enhanced_blurred"
            )

            # Compare results
            original_score = score_result(
                original_result
            )

            enhanced_score = score_result(
                enhanced_result
            )

            print(
                f"\nOriginal Score: {original_score}"
            )

            print(
                f"Enhanced Score: {enhanced_score}"
            )

            # Select better result
            if enhanced_score > original_score:

                final_result = enhanced_result

                print(
                    "Selected ENHANCED image result"
                )

            else:

                final_result = original_result

                print(
                    "Selected ORIGINAL image result"
                )

        # ----------------------------------------------------
        # FINAL DATA
        # ----------------------------------------------------

        final_data = final_result.get(
            "data"
        )

        # Safety fallback
        if final_data is None:

            final_data = {
                field: ""
                for field in REQUIRED_FIELDS
            }

        # Convert to JSON string to preserve your
        # existing raw_markdown backend response format.
        final_json_string = json.dumps(
            final_data,
            ensure_ascii=False
        )

        print("\nOCR COMPLETED")
        print(
            json.dumps(
                final_data,
                ensure_ascii=False,
                indent=2
            )
        )

        print("=" * 70)

        # ----------------------------------------------------
        # API RESPONSE
        # ----------------------------------------------------

        return JSONResponse(
            content={
                "success": True,

                # Backward compatible with your existing backend
                "raw_markdown": final_json_string,

                # Useful debugging information
                "validation_status": (
                    "valid"
                    if final_result.get("valid")
                    else "suspicious"
                ),

                "validation_issues": final_result.get(
                    "issues",
                    []
                ),

                "blur_score": round(
                    blur_score,
                    2
                ),

                "image_type": (
                    "blurred"
                    if is_blurry
                    else "clear"
                ),

                "selected_processing": final_result.get(
                    "image_label",
                    "unknown"
                )
            }
        )

    except Exception as e:

        print(
            "\nOCR ERROR:",
            str(e)
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
            }
        )
