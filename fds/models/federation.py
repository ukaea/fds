from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from fds.models.activity import ActivityType


class MemberRead(BaseModel):
    """A catalogue FDS asks when someone searches across catalogues."""

    id: str
    title: str


class DatasetQuery(BaseModel):
    """A dataset listing to ask each member for.

    ``device_name`` and ``shot_id`` say which listing: every dataset, a device's,
    or a shot's. The other fields are the listing's filters and paging, with the
    meanings they have on FDS's own dataset listings. A shot's listing has no
    ``scope``, ``shot_property`` or ``shot_id_prefix``, so they are left unset
    for one.
    """

    device_name: str | None = None
    shot_id: str | None = None
    scope: str | None = None
    name: str | None = None
    properties: list[str] = []
    shot_properties: list[str] = []
    activity_type: ActivityType | None = None
    source: str | None = None
    shot_id_prefix: str | None = None
    include_replaced: bool = False
    offset: int = 0
    limit: int


class AnswerStatus(StrEnum):
    """What came back from one member.

    ``answered``: the member applied the query, and these are its records.
    ``failed``: the member gave no answer FDS could use, in time or at all.
    """

    ANSWERED = "answered"
    FAILED = "failed"


class MemberAnswer(BaseModel):
    """One member's answer to a search, reported on its own.

    ``datasets`` are JSON-LD ``dcat:Dataset`` nodes written with the
    ``@context`` of the response that carries them. Each one's ``@id`` is the
    member's own identifier for the record, so a reader follows it to the
    member, where the record is kept. ``detail`` says why a member failed.
    """

    member: MemberRead
    status: AnswerStatus
    detail: str | None = None
    datasets: list[dict[str, Any]] = []


class FederatedSearch(BaseModel):
    """The answers of every member to one search, member by member."""

    context: dict[str, Any] = Field(serialization_alias="@context")
    answers: list[MemberAnswer]
