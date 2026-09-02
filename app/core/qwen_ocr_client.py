import cv2
import requests
import json
import numpy as np
from app.core.config import settings

def run_qwen_ocr(image: np.ndarray) -> dict:
    """
    Sends the cropped ROI image to the Qwen Colab OCR service.
    Returns the parsed JSON response.
    """
    if not settings.QWEN_OCR_API_URL:
        raise ValueError("QWEN_OCR_API_URL is not configured in environment.")

    # Convert image (numpy array BGR) to JPEG byte stream
    success, encoded_image = cv2.imencode('.jpg', image)
    if not success:
        raise RuntimeError("Failed to encode image to JPEG.")
    
    image_bytes = encoded_image.tobytes()

    try:
        response = requests.post(
            settings.QWEN_OCR_API_URL,
            files={"file": ("image.jpg", image_bytes, "image/jpeg")},
            timeout=120  # Model might take some time on T4 GPU
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to connect to Qwen OCR API: {str(e)}")

    try:
        result_json = response.json()
    except ValueError:
        raise RuntimeError("Qwen OCR API returned invalid JSON.")

    if not result_json.get("success"):
        raise RuntimeError(f"Qwen OCR API error: {result_json.get('error', 'Unknown error')}")

    raw_markdown = result_json.get("raw_markdown", "")
    
    try:
        # The prompt forces Qwen to return a JSON string
        # Clean up any potential markdown block markers
        clean_json_str = raw_markdown.strip()
        if clean_json_str.startswith("```json"):
            clean_json_str = clean_json_str[7:]
        if clean_json_str.endswith("```"):
            clean_json_str = clean_json_str[:-3]
            
        parsed_data = json.loads(clean_json_str.strip())
        return parsed_data
    except ValueError as e:
        raise RuntimeError(f"Failed to parse Qwen OCR JSON response: {str(e)}\nRaw Response: {raw_markdown}")
