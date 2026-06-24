import json
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

from app.core.config import config


def _json_serializer(obj: object) -> str:
    return json.dumps(
        obj, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o)
    )


engine = create_engine(
    config.db_url,
    connect_args={"check_same_thread": False},
    json_serializer=_json_serializer,
)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
