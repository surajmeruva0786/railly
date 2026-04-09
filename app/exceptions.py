from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


class NotFoundError(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(404, detail)


class UnauthorizedError(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(401, detail)


class ForbiddenError(AppException):
    def __init__(self, detail: str = "Not allowed"):
        super().__init__(403, detail)


class BadRequestError(AppException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(400, detail)


class ConflictError(AppException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(409, detail)


def register_error_handlers(app: FastAPI):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )
