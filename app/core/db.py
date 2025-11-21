from typing import Annotated
from fastapi import Depends
from sqlmodel import Session, create_engine
from app.core.config import config

engine = create_engine(config.db_url, connect_args={"check_same_thread": False})


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
