from fastapi import FastAPI

from app.core.config import config
from app.core.logging import setup_logging
from app.api.v1 import (
    catalog_router,
    device_router,
    source_router,
    shot_router,
    dataset_router,
)
from app.api.exception_handlers import add_exception_handlers


setup_logging()

app = FastAPI(title=config.app_name)

add_exception_handlers(app)

app.include_router(device_router.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(shot_router.router, prefix="/api/v1", tags=["shots"])
app.include_router(source_router.router, prefix="/api/v1/sources", tags=["sources"])
app.include_router(dataset_router.router, prefix="/api/v1", tags=["datasets"])
app.include_router(catalog_router.router, prefix="/api/v1", tags=["catalog"])
