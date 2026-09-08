from fastapi import HTTPException


class SaveStage:
    """
    Canonical stage names for the voter save flow. Reported back as
    `error.stage` so a failure can be attributed without reading the logs.
    """

    REQUEST_VALIDATION = "request_validation"
    CONSTITUENCY_RESOLUTION = "constituency_resolution"
    FIELD_VALIDATION = "field_validation"
    DATABASE_SAVE = "database_save"
    COMMIT = "commit"


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field: str = None,
        stage: str = None,
        details=None
    ):
        self.code = code
        self.message = message
        self.field = field
        # Additive diagnostics. `details` must only ever carry operator-safe
        # context (names, scores, counts) — never SQL text, tracebacks or
        # secrets; those go to the logs.
        self.stage = stage
        self.details = details

        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "field": field,
                "stage": stage,
                "details": details
            }
        )
