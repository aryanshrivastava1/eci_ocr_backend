import os
import threading

os.environ.setdefault("PYTHONUNBUFFERED", "1")

from fastapi import FastAPI
from app.db.session import engine
from app.db.base import Base

from app.api.routes import auth
from app.api.routes import ocr

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app.db.base_model import *  # important

from app.utils.exceptions import AppException, SaveStage
from app.core.logger import get_logger, log_stage_failure
from app.api.routes import voter

logger = get_logger("api")


app = FastAPI()

# Create tables
Base.metadata.create_all(bind=engine)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
app.include_router(voter.router, prefix="/voter", tags=["Voter"])


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    # `stage` and `details` are additive; `code`, `message` and `field` keep
    # their existing names, types and values for existing clients.
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "field": exc.field,
                "stage": getattr(exc, "stage", None),
                "details": getattr(exc, "details", None)
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """
    Pydantic rejects the payload before any route code runs, so a malformed
    save never reached a log line before. Report it as stage
    `request_validation` in the standard envelope, and keep the original
    `detail` key so clients parsing FastAPI's default 422 body still work.
    """
    raw = exc.errors()
    details = [
        {
            "field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"),
            "message": e.get("msg"),
            "type": e.get("type"),
        }
        for e in raw
    ]
    first_field = details[0]["field"] if details else None

    log_stage_failure(
        logger, SaveStage.REQUEST_VALIDATION,
        "payload rejected by request validation",
        path=request.url.path, errors=details,
    )

    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({
            "success": False,
            "error": {
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "Invalid request payload",
                "field": first_field,
                "stage": SaveStage.REQUEST_VALIDATION,
                "details": details
            },
            "detail": raw
        })
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Last resort. The full traceback goes to the backend log; the client gets a
    sanitised message with no SQL text, exception string or stack frames.
    """
    log_stage_failure(
        logger, "unhandled", "unhandled exception",
        path=request.url.path, exc=exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Something went wrong. Please try again.",
                "field": None,
                "stage": None,
                "details": None
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
