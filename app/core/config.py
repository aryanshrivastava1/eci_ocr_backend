from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    SARVAM_BASE_URL: str = os.getenv("SARVAM_BASE_URL")
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY")
    QWEN_OCR_API_URL: str = os.getenv("QWEN_OCR_API_URL")

    # Comma-separated list of allowed browser origins for the web frontend.
    # "*" (the default) allows any origin; credentials are never allowed with
    # "*", which is safe here because auth uses Authorization: Bearer, not cookies.
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

settings = Settings()