from typing import Any
from urllib.parse import quote

import httpx
from pyld import jsonld

from fds.models.federation import DatasetQuery
from fds.services.jsonld import generate_context

LD_JSON = "application/ld+json"
API_VERSION = "/v1"

# The node types FDS lists from a member's answer. The answer's other nodes,
# such as the member's catalogue records of its datasets, are left out.
_RECORD_TYPES = {
    "http://www.w3.org/ns/dcat#Dataset",
    "http://www.w3.org/ns/dcat#Catalog",
}


class UnreadableAnswer(ValueError):
    """The member did not answer in JSON-LD that FDS can read."""


def in_fds_context(document: Any) -> list[dict[str, Any]]:
    """The records in a member's JSON-LD answer, each written with FDS's context.

    A record is a ``dcat:Dataset`` or ``dcat:Catalog`` node with an ``@id`` at
    the top of the answer. Each is expanded with the member's own context and
    compacted again with FDS's, so the terms FDS knows read as they do in FDS's
    own records whatever prefixes the member chose, and terms FDS does not know
    keep their full IRIs. The answer's context must be written out in it: FDS
    fetches no context from elsewhere.
    """
    # Refusing every remote document keeps a member from making FDS fetch an
    # address of its choosing.
    refuse = jsonld.dummy_document_loader()
    context = {"@context": generate_context()}
    try:
        expanded = jsonld.expand(document, {"documentLoader": refuse})
        records = [
            node
            for node in expanded
            if "@id" in node and _RECORD_TYPES & set(node.get("@type", []))
        ]
        compacted = [
            jsonld.compact(node, context, {"documentLoader": refuse})
            for node in records
        ]
    except jsonld.JsonLdError as error:
        raise UnreadableAnswer("answered with JSON-LD that FDS cannot read") from error
    return [
        {key: value for key, value in node.items() if key != "@context"}
        for node in compacted
        if isinstance(node, dict)
    ]


def _path(query: DatasetQuery) -> str:
    """The member's dataset listing that answers ``query``."""
    if query.device_name is None:
        return f"{API_VERSION}/datasets"
    device = quote(query.device_name, safe="")
    if query.shot_id is None:
        return f"{API_VERSION}/devices/{device}/datasets"
    shot = quote(query.shot_id, safe="")
    return f"{API_VERSION}/devices/{device}/shots/{shot}/datasets"


def _params(query: DatasetQuery) -> tuple[tuple[str, str], ...]:
    """``query``'s filters and paging, as FDS's dataset listings take them."""
    params = [("offset", str(query.offset)), ("limit", str(query.limit))]
    if query.scope is not None:
        params.append(("scope", query.scope))
    if query.name is not None:
        params.append(("name", query.name))
    params += [("property", token) for token in query.properties]
    params += [("shot_property", token) for token in query.shot_properties]
    if query.activity_type is not None:
        params.append(("activity_type", query.activity_type.value))
    if query.source is not None:
        params.append(("source", query.source))
    if query.shot_id_prefix is not None:
        params.append(("shot_id_prefix", query.shot_id_prefix))
    if query.include_replaced:
        params.append(("include_replaced", "true"))
    return tuple(params)


def search(client: httpx.Client, url: str, query: DatasetQuery) -> list[dict[str, Any]]:
    """The datasets another FDS lists for ``query``, as JSON-LD nodes.

    ``url`` is the address of the member's API, without a version: the member
    is asked at ``API_VERSION`` for the same listing, with the same filters and
    paging, in JSON-LD. A member that has no such device or shot answers with no
    datasets.
    """
    response = client.get(
        f"{url}{_path(query)}", params=_params(query), headers={"Accept": LD_JSON}
    )
    response.raise_for_status()
    # An FDS too old to answer listings in JSON-LD sends its plain JSON listing
    # whatever the Accept header asks for.
    if not response.headers.get("content-type", "").startswith(LD_JSON):
        raise UnreadableAnswer("did not answer in JSON-LD")
    try:
        document = response.json()
    except ValueError as error:
        raise UnreadableAnswer("answered with something other than JSON") from error
    return in_fds_context(document)
