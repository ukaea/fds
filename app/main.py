from fastapi import APIRouter, FastAPI

from app import __version__
from app.api.exception_handlers import add_exception_handlers
from app.api.identifiers import router as identifier_router
from app.api.middleware import AuditMiddleware
from app.api.v1 import (
    activity_router,
    catalog_router,
    collection_router,
    dataset_router,
    device_router,
    federation_router,
    file_access_router,
    shot_router,
    source_router,
)
from app.core.config import config
from app.core.db import engine
from app.core.logging import setup_logging
from app.core.telemetry import setup_telemetry

setup_logging()

app = FastAPI(title=config.app_name, version=__version__)

app.add_middleware(AuditMiddleware)
setup_telemetry(app, engine)

add_exception_handlers(app)


@app.get("/health", tags=["health"], summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# The API's version. Every versioned route sits under it; the identifiers and
# /health carry no version.
v1 = APIRouter(prefix="/v1")
v1.include_router(device_router.router, prefix="/devices", tags=["devices"])
v1.include_router(shot_router.router, tags=["shots"])
v1.include_router(source_router.router, prefix="/sources", tags=["sources"])
v1.include_router(activity_router.router, prefix="/activities", tags=["activities"])
v1.include_router(dataset_router.router, tags=["datasets"])
v1.include_router(collection_router.router, tags=["collections"])
v1.include_router(catalog_router.router, tags=["catalog"])
v1.include_router(
    file_access_router.router, prefix="/file-access", tags=["file-access"]
)
v1.include_router(federation_router.router, prefix="/federation", tags=["federation"])

app.include_router(identifier_router)
app.include_router(v1)
