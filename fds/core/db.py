import json
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

# Imported for its side effect: registers the ORM audit listeners.
from fds.core import audit  # noqa: F401
from fds.core.config import config


def _json_serializer(obj: object) -> str:
    return json.dumps(
        obj, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o)
    )


def make_engine(url: str) -> Engine:
    return create_engine(
        url,
        json_serializer=_json_serializer,
        pool_pre_ping=True,
        # PostgreSQL compiles a query it estimates to be expensive, and the
        # metadata walk is estimated far above its real cost. Compiling took
        # longer than it saved on every query measured.
        connect_args={"options": "-c jit=off"},
    )


engine = make_engine(config.db_url)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
