from fastapi import APIRouter, FastAPI
from starlette.routing import Route

from fds import __version__
from fds.api.exception_handlers import add_exception_handlers
from fds.api.identifiers import router as identifier_router
from fds.api.middleware import AuditMiddleware
from fds.api.protected_resource import router as protected_resource_router
from fds.api.v1 import (
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
from fds.core.config import config
from fds.core.db import engine
from fds.core.logging import setup_logging
from fds.core.telemetry import setup_telemetry
from fds.mcp.server import mcp
from fds.mcp.sign_in import RefuseInvalidTokens

setup_logging()

mcp_app = mcp.http_app(path="/mcp", stateless_http=True)

app = FastAPI(title=config.app_name, version=__version__, lifespan=mcp_app.lifespan)

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
app.include_router(protected_resource_router)
app.include_router(v1)
# A route rather than a mount: a mount answers /mcp with a redirect to /mcp/, which
# not every MCP client follows.
app.router.routes.append(Route("/mcp", RefuseInvalidTokens(mcp_app)))
