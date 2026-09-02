from supabase import create_client, Client
from app.core.config import settings
import uuid
import mimetypes

# Initialize client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)

BUCKET_NAME = "ocr-images"

def upload_image(file_bytes: bytes, user_id: str, job_id: str, filename: str):
    ext = filename.split(".")[-1]
    unique_name = f"{uuid.uuid4()}.{ext}"

    file_path = f"{user_id}/{job_id}/{unique_name}"

    content_type, _ = mimetypes.guess_type(filename)

    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": content_type or "application/octet-stream"}
        )
    except Exception as e:
        raise Exception(f"Upload failed: {str(e)}")  # ✅ HARD FAIL

    # 🔥 verify file exists (VERY IMPORTANT)
    files = supabase.storage.from_(BUCKET_NAME).list(f"{user_id}/{job_id}")

    if not files:
        raise Exception("Upload verification failed: file not found in bucket")

    # Return the file_path instead of public URL so worker can use SDK to download
    return file_path