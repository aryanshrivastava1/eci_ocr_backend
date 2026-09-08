"""
Structured, stage-aware logging.

The save flow moves through five named stages (see SaveStage in
app/utils/exceptions.py). When a save fails, the operator needs to know which
stage failed and with what context — without that, every failure looks like the
same opaque 500.

This module is observability only: it never changes control flow, and
log_stage_failure() deliberately keeps the full internal detail (SQL text,
tracebacks) on the backend. Nothing here is ever handed to a client.
"""

import io
import logging
import os
import sys

_CONFIGURED = False
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def _stream():
    """
    UTF-8 stream for the handler. Constituency and district names are Hindi,
    and on a cp1252 Windows console a plain sys.stdout handler raises
    UnicodeEncodeError instead of logging the line.
    """
    try:
        return io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8",
            errors="backslashreplace", line_buffering=True,
        )
    except Exception:
        return sys.stdout


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger("pramaan")
    if not root.handlers:
        handler = logging.StreamHandler(_stream())
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)

    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Logger under the 'pramaan' namespace, configured on first use."""
    _configure()
    return logging.getLogger(f"pramaan.{name}")


def _context(stage: str, user_id=None, extra: dict = None) -> str:
    parts = [f"stage={stage}"]
    if user_id is not None:
        parts.append(f"user_id={user_id}")
    if extra:
        parts.extend(f"{k}={v!r}" for k, v in extra.items())
    return " ".join(parts)


def log_stage_start(logger, stage: str, user_id=None, **extra) -> None:
    logger.info("START   %s", _context(stage, user_id, extra))


def log_stage_success(logger, stage: str, user_id=None, **extra) -> None:
    logger.info("OK      %s", _context(stage, user_id, extra))


def log_stage_failure(logger, stage: str, message: str, user_id=None,
                      exc: BaseException = None, **extra) -> None:
    """
    Backend-only failure record. `exc` is logged with its full traceback so the
    root cause (including the SQL statement) is recoverable from the logs while
    the API response stays sanitised.
    """
    logger.error(
        "FAIL    %s reason=%r", _context(stage, user_id, extra), message,
        exc_info=exc if exc is not None else False,
    )
