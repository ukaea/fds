from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .shot import Shot
    from .source import Source


class ShotSource(SQLModel, table=True):
    shot_id: int | None = Field(
        default=None, foreign_key="shot.id", primary_key=True
    )
    source_id: int | None = Field(
        default=None, foreign_key="source.id", primary_key=True
    )
    quality_flag: str | None = Field(default=None, index=True)

    shot: "Shot" = Relationship(back_populates="source_links")
    source: "Source" = Relationship(back_populates="shot_links")
