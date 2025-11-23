from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .shotsource import ShotSource


class SourceBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str | None = None


class Source(SourceBase, table=True):
    id: int | None = Field(default=None, primary_key=True, index=True)

    shot_links: list["ShotSource"] = Relationship(back_populates="source")



class SourceCreate(SourceBase):
    pass


class SourceRead(SourceBase):
    id: int


class SourceUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
