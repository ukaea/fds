from fastapi import FastAPI

from app.api.exception_handlers import add_exception_handlers
from app.api.middleware import AuditMiddleware
from app.api.v1 import (
    activity_router,
    catalog_router,
    collection_router,
    dataset_router,
    device_router,
    file_access_router,
    shot_router,
    source_router,
)
from app.core.config import config
from app.core.db import engine
from app.core.logging import setup_logging
from app.core.telemetry import setup_telemetry

setup_logging()

app = FastAPI(title=config.app_name)

app.add_middleware(AuditMiddleware)
setup_telemetry(app, engine)

add_exception_handlers(app)


@app.get("/health", tags=["health"], summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(device_router.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(shot_router.router, prefix="/api/v1", tags=["shots"])
app.include_router(source_router.router, prefix="/api/v1/sources", tags=["sources"])
app.include_router(
    activity_router.router, prefix="/api/v1/activities", tags=["activities"]
)
app.include_router(dataset_router.router, prefix="/api/v1", tags=["datasets"])
app.include_router(collection_router.router, prefix="/api/v1", tags=["collections"])
app.include_router(catalog_router.router, prefix="/api/v1", tags=["catalog"])
app.include_router(
    file_access_router.router, prefix="/api/v1/file-access", tags=["file-access"]
)
