from fastapi import FastAPI

from app.core.config import config
from app.core.logging import setup_logging
from app.api.v1 import device_router, source_router


setup_logging()

app = FastAPI(title=config.app_name)


app.include_router(device_router.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(source_router.router, prefix="/api/v1/sources", tags=["sources"])
