import cv2
import numpy as np
import os
from supabase import create_client
from app.core.config import settings


def download_image(image_path: str):
    # Initialize a fresh client for the worker thread to avoid stale keep-alive connections
    local_supabase = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )
    
    try:
        image_bytes = local_supabase.storage.from_("ocr-images").download(image_path)
    except Exception as e:
        raise Exception(f"Download failed: {str(e)}")

    image_array = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None:
        raise Exception("OpenCV failed to decode image")

    return image


def crop_rois(image: np.ndarray):
    """
    Crop required regions:
    - top_left (structured data)
    - form_section (mobile number area)
    """
    h, w = image.shape[:2]

    # ROI 1: top-left
    top_left = image[0:int(h * 0.25), 0:int(w * 0.6)]

    # ROI 2: form upper section
    form_section = image[int(h * 0.25):int(h * 0.55), :]

    return top_left, form_section

def enhance_cropped(image):
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # contrast (keep as is)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)

    # 🔥 VERY LIGHT denoise (key)
    denoised = cv2.fastNlMeansDenoising(
        enhanced,
        None,
        h=10,   # keep LOW (important)
        templateWindowSize=7,
        searchWindowSize=21
    )

    return denoised

def enhance_printed(image):
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # 1️⃣ shadow removal (keep this)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 35))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    norm = cv2.divide(gray, bg, scale=255)

    # 2️⃣ light contrast (only this)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(norm)

    return enhanced

def enhance_handwritten(image):
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # light blur
    blur = cv2.GaussianBlur(gray, (3,3), 0)

    # 🔥 stronger contrast
    alpha = 1.8   # was 1.6 → increase
    beta = 5      # small brightness

    enhanced = cv2.convertScaleAbs(blur, alpha=alpha, beta=beta)

    # 🔥 slight sharpening (important)
    kernel = np.array([
        [0, -1, 0],
        [-1, 5,-1],
        [0, -1, 0]
    ])
    sharpened = cv2.filter2D(enhanced, -1, kernel)

    return sharpened

def normalize_lighting(image):
    # convert only if needed
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15,15))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

    normalized = cv2.divide(gray, bg, scale=255)

    return normalized

def remove_shadow(image):
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # large kernel for document lighting
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 35))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

    # 🔥 KEY CHANGE: division instead of subtraction
    normalized = cv2.divide(gray, bg, scale=255)

    return normalized

def save_debug_images(job_id: str, top_left, form_section):
    base_path = os.path.abspath("debug")   # 🔥 absolute path

    os.makedirs(base_path, exist_ok=True)

    top_path = os.path.join(base_path, f"{job_id}_top_left.jpg")
    form_path = os.path.join(base_path, f"{job_id}_form.jpg")

    cv2.imwrite(top_path, top_left)
    cv2.imwrite(form_path, form_section)

    print(f"Saved debug images at: {base_path}")  # 🔥 add this