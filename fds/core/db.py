import json
from time import perf_counter
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Connection, Engine, event
from sqlmodel import Session, create_engine

# Imported for its side effect: registers the ORM audit listeners.
from fds.core import audit  # noqa: F401
from fds.core.config import config
from fds.core.context import record_query

_QUERY_STARTED = "fds_query_started"


def _json_serializer(obj: object) -> str:
    return json.dumps(
        obj, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o)
    )


def _start_query_clock(conn: Connection, *_: object) -> None:
    conn.info[_QUERY_STARTED] = perf_counter()


def _stop_query_clock(conn: Connection, *_: object) -> None:
    # A query that raises never gets here, and the next query on the connection
    # overwrites its start, so only queries that finished are counted.
    started = conn.info.pop(_QUERY_STARTED, None)
    if started is not None:
        record_query(perf_counter() - started)


def make_engine(url: str) -> Engine:
    engine = create_engine(
        url,
        json_serializer=_json_serializer,
        pool_pre_ping=True,
        # PostgreSQL compiles a query it estimates to be expensive, and the
        # metadata walk is estimated far above its real cost. Compiling took
        # longer than it saved on every query measured.
        connect_args={"options": "-c jit=off"},
    )
    # So each request's log line can say how much of its time was spent waiting
    # on the database.
    event.listen(engine, "before_cursor_execute", _start_query_clock)
    event.listen(engine, "after_cursor_execute", _stop_query_clock)
    return engine


engine = make_engine(config.db_url)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
