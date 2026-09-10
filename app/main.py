import os
import threading

os.environ.setdefault("PYTHONUNBUFFERED", "1")

from fastapi import FastAPI
from app.db.session import engine
from app.db.base import Base

from app.api.routes import auth
from app.api.routes import ocr

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app.db.base_model import *  # important

from app.core.config import settings
from app.utils.exceptions import AppException
from app.api.routes import voter
from app.api.routes import geo


app = FastAPI()

# CORS — origins come from the CORS_ORIGINS env var (comma-separated).
# Native Flutter clients ignore CORS; this exists for the Flutter web build.
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
_allow_all = "*" in _origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else _origins,
    # Auth is Authorization: Bearer, not cookies, so credentials stay off when
    # origins are wildcarded (the CORS spec forbids "*" together with credentials).
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables
Base.metadata.create_all(bind=engine)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
app.include_router(voter.router, prefix="/voter", tags=["Voter"])
app.include_router(geo.router, prefix="/geo", tags=["Geo"])


@app.get("/health", tags=["Health"])
def health():
    """Liveness probe for Render's health check — no DB or OCR dependency."""
    return {"status": "ok"}


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "field": exc.field
            }
        }
    )


@app.on_event("startup")
def start_worker():
    if os.getenv("OCR_BACKEND", "local") == "colab":
        from app.workers.colab_ocr_worker import worker
    else:
        from app.workers.ocr_worker import worker
    print("Starting OCR worker...")
    t = threading.Thread(target=worker, daemon=True)
    t.start()
