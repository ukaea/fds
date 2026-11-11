from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from typing import Any

import httpx
import structlog

from fds.core.config import FederationMember
from fds.models.federation import AnswerStatus, DatasetQuery, MemberAnswer, MemberRead
from fds.services import fds_gateway

logger = structlog.get_logger(__name__)

# How FDS asks each kind of member for the datasets that answer a query.
type Gateway = Callable[[httpx.Client, str, DatasetQuery], list[dict[str, Any]]]
_GATEWAYS: dict[str, Gateway] = {"fds": fds_gateway.search}


def _failure(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "did not answer in time"
    if isinstance(error, httpx.HTTPStatusError):
        return f"answered with HTTP {error.response.status_code}"
    return "could not be reached"


class FederationService:
    """Asks the member catalogues for their records when a search arrives.

    Nothing a member returns is stored. Members are asked anonymously, so a
    caller sees the records a member shows anyone, whoever the caller is.
    ``transport`` replaces the network, for tests.
    """

    def __init__(
        self,
        members: list[FederationMember],
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.members = members
        self.timeout = timeout
        self.transport = transport

    def list_members(self) -> list[MemberRead]:
        return [MemberRead(id=member.id, title=member.title) for member in self.members]

    def search(self, query: DatasetQuery) -> list[MemberAnswer]:
        """Each member's answer to ``query``, in the order the members are listed.

        The members are asked at the same time, so a search takes as long as the
        slowest of them, up to the timeout.
        """
        if not self.members:
            return []
        with ThreadPoolExecutor(max_workers=len(self.members)) as pool:
            return list(pool.map(self._ask, self.members, repeat(query)))

    def _ask(self, member: FederationMember, query: DatasetQuery) -> MemberAnswer:
        read = MemberRead(id=member.id, title=member.title)
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport, follow_redirects=True
            ) as client:
                datasets = _GATEWAYS[member.kind](client, member.url, query)
        except fds_gateway.UnreadableAnswer as error:
            logger.warning("federation_member_unreadable", member=member.id)
            return MemberAnswer(
                member=read, status=AnswerStatus.FAILED, detail=str(error)
            )
        except httpx.HTTPError as error:
            logger.warning(
                "federation_member_failed", member=member.id, error=repr(error)
            )
            return MemberAnswer(
                member=read, status=AnswerStatus.FAILED, detail=_failure(error)
            )
        return MemberAnswer(
            member=read, status=AnswerStatus.ANSWERED, datasets=datasets
        )
