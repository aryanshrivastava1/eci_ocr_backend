from fastapi import HTTPException


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field: str = None,
        data: dict = None,
    ):
        self.code = code
        self.message = message
        self.field = field
        self.data = data

        detail = {
            "code": code,
            "message": message,
            "field": field,
        }

        # Only added when a caller supplies it, so every existing error
        # response keeps its exact previous shape.
        if data is not None:
            detail["data"] = data

        super().__init__(
            status_code=status_code,
            detail=detail,
        )
