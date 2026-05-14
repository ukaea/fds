from typing import Any

from sqlmodel import SQLModel


class ScientificProperty(SQLModel):
    name: str
    value: Any
    unit: str | None = None
    description: str | None = None
