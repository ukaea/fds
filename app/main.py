from fastapi import FastAPI

from app.core.config import config
from app.core.logging import setup_logging


setup_logging()

app = FastAPI(title=config.app_name)


# app.include_router()
