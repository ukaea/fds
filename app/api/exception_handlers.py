from fastapi import Request
from fastapi.responses import JSONResponse
from app.services.exceptions import (
    DeviceNotFoundError,
    ShotContextError,
    ForbiddenError,
    UnauthorizedError,
    ResourceNotFoundError,
    FDSValidationError,
    ConflictError
)

def add_exception_handlers(app):
    @app.exception_handler(DeviceNotFoundError)
    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found_handler(_request: Request, exc: Exception):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ShotContextError)
    async def shot_context_handler(_request: Request, exc: ShotContextError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(_request: Request, exc: ForbiddenError):
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc)},
        )

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(_request: Request, exc: UnauthorizedError):
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
        )

    @app.exception_handler(FDSValidationError)
    async def validation_error_handler(_request: Request, exc: FDSValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(_request: Request, exc: ConflictError):
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )
