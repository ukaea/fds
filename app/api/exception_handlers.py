import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry import trace

from app.core.logging import mark_logged
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
    ShotContextError,
    UnauthorizedError,
)

logger = structlog.get_logger(__name__)


def _context(request: Request, exc: Exception) -> dict[str, str | None]:
    """The parts of a failed request worth recording."""
    return {
        "method": request.method,
        "path": request.url.path,
        "detail": str(exc),
        "error_type": type(exc).__name__,
    }


def _current_trace_id() -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return trace.format_trace_id(span_context.trace_id)


def add_exception_handlers(app):
    @app.exception_handler(DeviceNotFoundError)
    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found_handler(request: Request, exc: Exception):
        logger.debug("request.not_found", **_context(request, exc))
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ShotContextError)
    async def shot_context_handler(request: Request, exc: ShotContextError):
        logger.debug("request.not_found", **_context(request, exc))
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(request: Request, exc: ForbiddenError):
        logger.warning("access.denied", **_context(request, exc))
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc)},
        )

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError):
        logger.warning("access.unauthenticated", **_context(request, exc))
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
        )

    @app.exception_handler(FDSValidationError)
    async def validation_error_handler(request: Request, exc: FDSValidationError):
        logger.info("request.invalid", **_context(request, exc))
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        logger.info("request.conflict", **_context(request, exc))
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.error("request.failed", exc_info=exc, **_context(request, exc))
        mark_logged(exc)
        content: dict[str, str] = {"detail": "Internal server error"}
        trace_id = _current_trace_id()
        if trace_id:
            content["trace_id"] = trace_id
        return JSONResponse(status_code=500, content=content)
