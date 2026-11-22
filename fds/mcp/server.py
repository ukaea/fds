import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

import httpx2 as httpx
from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.exceptions import ToolError
from fastmcp.prompts import Message
from fastmcp.server.dependencies import get_context, get_http_request
from fastmcp.server.lifespan import lifespan
from mcp_types import (
    CompletionArgument,
    CompletionContext,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    EmbeddedResource,
    InputRequiredResult,
    InputResponse,
    PromptReference,
    ResourceTemplateReference,
    TextResourceContents,
    ToolAnnotations,
)
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import Field

from fds import __version__
from fds.mcp.catalogue import Catalogue, without_empty

INSTRUCTIONS = """\
These tools read a Fusion Data Service (FDS) catalogue: records of fusion
experiments and simulations. A device (such as the MAST tokamak) has shots; a
shot has properties (scientific metadata such as confinement_mode or
plasma_current_max) and datasets; datasets are grouped into collections and
record the Activity (measurement, analysis, simulation, calibration) that
produced them.

To answer a question about shots:
1. If the question does not say which device, leave `device` out of
   describe_shot_properties and search_shots: the user is asked to choose.
   Their results then carry `device_chosen_by_user`. Answer for that device
   only. If it holds nothing that answers the question, say so, and ask
   before searching another device.
2. describe_shot_properties, to learn which properties exist, their values and
   their units. Only filter on properties and values it reports, and give
   bounds in the unit it gives (plasma current in A: 700 kA is 700000).
3. search_shots with those filters. Then search_datasets or get_shot for what
   was recorded on the shots found.

Every record carries a `link` to its page in the catalogue: give it to the user
when you name a record. Listings return one page; `next_offset` means there are
more, and passing it as `offset` fetches the next page. Answer from what the
tools return, not from what you know about the device. When a search finds
nothing, say so rather than guessing.
"""


@lifespan
async def connect_to_fds(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """One HTTP client for the server's lifetime, whose requests go to FDS's own
    app in this process rather than over the network. An error inside the app
    comes back as a 500 response, as it would to any other client."""
    # Imported here rather than at the top: fds.main imports this module to
    # mount the server, so the app only exists once both modules are loaded.
    from fds.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        headers={"Accept": "application/json"},
        timeout=30,
    ) as http:
        yield {"fds": http}


def catalogue_for_caller(ctx: Annotated[Context, CurrentContext()]) -> Catalogue:
    """A Catalogue that reads as the person making this MCP request: at the
    address they reached FDS on, with the token they sent, if any."""
    request = get_http_request()
    return Catalogue(
        ctx.lifespan_context["fds"],
        api=f"{request.url.scheme}://{request.url.netloc}/v1",
        authorization=request.headers.get("authorization"),
    )


CatalogueDep = Annotated[Catalogue, Depends(catalogue_for_caller)]
ContextDep = Annotated[Context | None, CurrentContext()]

PropertyFilters = Annotated[
    list[str] | None,
    Field(
        description="`name` matches records carrying the property; `name:value` "
        "matches that value, such as `confinement_mode:H-mode`. A property inside "
        "a group is named by its path, such as `nbi.beam.source:SW`. Two values "
        "of one property match either; different properties must all match."
    ),
]
Bounds = Annotated[
    list[str] | None,
    Field(
        description="`name:number`, a bound on a numeric property in the unit "
        "describe_shot_properties gives, such as `plasma_current_max:700000`."
    ),
]
Offset = Annotated[
    int, Field(ge=0, description="Where the page starts: an earlier `next_offset`.")
]
Limit = Annotated[int, Field(ge=1, le=50, description="Records per page, 50 at most.")]
ActivityType = Literal["measurement", "analysis", "simulation", "calibration"]

READ_ONLY = ToolAnnotations(read_only_hint=True)

mcp = FastMCP(
    "fds",
    instructions=INSTRUCTIONS,
    version=__version__,
    lifespan=connect_to_fds,
    mask_error_details=True,
)


@mcp.tool(annotations=READ_ONLY)
async def list_devices(catalogue: CatalogueDep) -> dict[str, Any]:
    """The devices this catalogue holds records for, such as tokamaks. Every shot
    search names one of them."""
    devices = await catalogue.get("/devices/")
    return {
        "devices": [
            without_empty(
                {
                    "name": device["name"],
                    "title": device.get("title"),
                    "description": device.get("description"),
                    "link": await catalogue.landing_page(f"/devices/{device['name']}"),
                }
            )
            for device in devices
        ]
    }


@mcp.tool(annotations=READ_ONLY)
async def describe_shot_properties(
    catalogue: CatalogueDep,
    ctx: ContextDep = None,
    device: str | None = None,
    property: PropertyFilters = None,
    property_min: Bounds = None,
    property_max: Bounds = None,
    id_prefix: str | None = None,
) -> dict[str, Any] | InputRequiredResult:
    """What a device's shots record, for building a search_shots filter. Call it
    before searching.

    Returns `total`, the number of shots in scope, and one entry per property:
    its `name`, how many shots carry it (`records`), its `kind`, `unit` and
    `description`, how many `distinct` values it has, `min` and `max` for numbers,
    and the `values` themselves when there are few enough to list. A property that
    every shot in scope has with the same value is left out.

    The counts and values answer questions such as "did any shot…" or "how
    many shots…" on their own: when `values` lists every value a property
    takes, there is no need to search the shots to check. `total` minus
    `records` is the number of shots that do not record the property.

    Pass the filters you plan to search with to see what remains once they apply.

    Args:
        device: The device's name, such as `mast`. Leave it out when the
            question does not say: the user is asked to choose, and the result
            carries `device_chosen_by_user`. Answer for that device only.
        id_prefix: Only shots whose ID starts with this.
    """
    chosen = await device_to_search(catalogue, ctx, device)
    if isinstance(chosen, InputRequiredResult):
        return chosen
    device, chosen_by_user = chosen
    summary = await catalogue.get(
        f"/devices/{device}/shots/properties",
        {
            "property": property,
            "property_min": property_min,
            "property_max": property_max,
            "id_prefix": id_prefix,
        },
    )
    return {**device_searched(device, chosen_by_user), **summary}


@mcp.tool(annotations=READ_ONLY)
async def find_property_values(
    catalogue: CatalogueDep,
    device: str,
    name: str,
    contains: str | None = None,
    limit: Limit = 20,
) -> dict[str, Any]:
    """The values one shot property takes on a device, most common first, with
    the number of shots that have each. For a property with too many values for
    describe_shot_properties to list.

    Args:
        device: The device's name, such as `mast`.
        name: The property's name, or its path for a property inside a group.
        contains: Only values containing this text, ignoring case.
    """
    return await catalogue.get(
        f"/devices/{device}/shots/properties/{name}/values",
        {"q": contains, "limit": limit},
    )


@mcp.tool(annotations=READ_ONLY)
async def search_shots(
    catalogue: CatalogueDep,
    ctx: ContextDep = None,
    device: str | None = None,
    property: PropertyFilters = None,
    property_min: Bounds = None,
    property_max: Bounds = None,
    id_prefix: str | None = None,
    offset: Offset = 0,
    limit: Limit = 20,
) -> dict[str, Any] | InputRequiredResult:
    """Find a device's shots by their properties, using the names, values and
    units describe_shot_properties reports. Returns each shot's ID, time and
    properties, without the properties' descriptions.

    Args:
        device: The device's name, such as `mast`. Leave it out when the
            question does not say: the user is asked to choose, and the result
            carries `device_chosen_by_user`. Answer for that device only.
        id_prefix: Only shots whose ID starts with this: `304` finds 30400-30499.
    """
    chosen = await device_to_search(catalogue, ctx, device)
    if isinstance(chosen, InputRequiredResult):
        return chosen
    device, chosen_by_user = chosen
    shots, paging = await catalogue.page(
        f"/devices/{device}/shots",
        {
            "property": property,
            "property_min": property_min,
            "property_max": property_max,
            "id_prefix": id_prefix,
        },
        offset,
        limit,
    )
    return {
        **device_searched(device, chosen_by_user),
        "shots": [await shot_summary(catalogue, shot) for shot in shots],
        **paging,
    }


async def device_to_search(
    catalogue: Catalogue, ctx: Context | None, device: str | None
) -> tuple[str, bool] | InputRequiredResult:
    """The device a shot tool works on, and whether the user chose it: the one the
    model gave, else the catalogue's only device, else the one the user picks when
    asked. The tool runs again with the user's answer, which arrives in
    `ctx.input_responses`."""
    if device:
        return device, False
    answers = ctx.input_responses if ctx else None
    if answers and "device" in answers:
        return device_chosen(answers["device"]), True
    devices = await catalogue.get("/devices/")
    if len(devices) == 1:
        return devices[0]["name"], False
    if ctx is None or not can_ask_the_user(ctx):
        names = ", ".join(d["name"] for d in devices)
        raise ToolError(f"Give `device`: this catalogue holds {names}.")
    return ask_for_device(devices)


def device_searched(device: str, chosen_by_user: bool) -> dict[str, Any]:
    """Which device a result covers, and whether the user chose it when asked, so
    the model can tell an answer for that device from an answer for another."""
    if chosen_by_user:
        return {"device": device, "device_chosen_by_user": True}
    return {"device": device}


def can_ask_the_user(ctx: Context) -> bool:
    """Whether the client can show the user a question: on the protocol that asks
    by returning an InputRequiredResult, and only if it accepts questions."""
    capabilities = ctx.session.client_capabilities
    return (
        ctx.request_context is not None
        and ctx.request_context.protocol_version in MODERN_PROTOCOL_VERSIONS
        and capabilities is not None
        and capabilities.elicitation is not None
    )


def ask_for_device(devices: list[dict[str, Any]]) -> InputRequiredResult:
    """A form with one field, labelled Device, whose choices show each device's
    title, such as MAST Upgrade, and send back its name, such as `mastu`."""
    choices = [
        {"const": device["name"], "title": device.get("title") or device["name"]}
        for device in devices
    ]
    question = ElicitRequestFormParams(
        message="Which device do you mean?",
        requested_schema={
            "type": "object",
            "properties": {
                "device": {"type": "string", "title": "Device", "oneOf": choices}
            },
            "required": ["device"],
        },
    )
    return InputRequiredResult(
        result_type="input_required",
        input_requests={
            "device": ElicitRequest(method="elicitation/create", params=question)
        },
    )


def device_chosen(answer: InputResponse) -> str:
    if not isinstance(answer, ElicitResult):
        raise ToolError("The answer about the device was not a reply to a question.")
    if answer.action != "accept" or not answer.content:
        raise ToolError(
            "The user did not choose a device, so nothing was searched. Ask them "
            "which device they mean."
        )
    return str(answer.content["device"])


@mcp.tool(annotations=READ_ONLY)
async def get_shot(catalogue: CatalogueDep, device: str, shot: str) -> dict[str, Any]:
    """One shot: every property with its description and extent, the datasets
    recorded on it and the collections it belongs to. It lists every dataset on
    the shot, so there is no need to call search_datasets for the shot as well.

    Args:
        device: The device's name, such as `mast`.
        shot: The shot's ID, such as `30421`.
    """
    path = f"/devices/{device}/shots/{shot}"
    (
        record,
        (datasets, dataset_paging),
        (collections, collection_paging),
    ) = await asyncio.gather(
        catalogue.get(path),
        catalogue.page(f"{path}/datasets", {}, 0, 50),
        catalogue.page(f"{path}/collections", {}, 0, 50),
    )
    return {
        **await shot_summary(catalogue, record, full=True),
        "datasets": [await dataset_summary(catalogue, d) for d in datasets],
        "more_datasets": "next_offset" in dataset_paging,
        "collections": [await collection_summary(catalogue, c) for c in collections],
        "more_collections": "next_offset" in collection_paging,
    }


@mcp.tool(annotations=READ_ONLY)
async def search_datasets(
    catalogue: CatalogueDep,
    device: str | None = None,
    shot: str | None = None,
    name: str | None = None,
    property: PropertyFilters = None,
    shot_property: PropertyFilters = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    offset: Offset = 0,
    limit: Limit = 20,
) -> dict[str, Any]:
    """Find datasets. A dataset is one body of data with its own record, such as
    one shot's equilibrium reconstruction, and may be stored in several formats.
    Returns a summary of each; get_dataset gives the full record.

    Args:
        device: Only this device's datasets.
        shot: Only this shot's datasets. Needs `device`.
        name: Only datasets with this exact name, such as `equilibrium`.
        property: Filters on the dataset's own properties.
        shot_property: Filters on the properties of the dataset's shot, in the
            forms `property` takes. `name=equilibrium` with
            `shot_property=confinement_mode:H-mode` finds the equilibria of
            H-mode shots. Not used with `shot`.
        activity_type: The kind of Activity that produced the dataset.
        source: The name of the source (software, facility or person) that
            carried out the Activity, such as `efit` or `jintrac`.
    """
    if shot and not device:
        raise ToolError("Give `device` with `shot`: shot IDs are per device.")
    params: dict[str, Any] = {
        "name": name,
        "property": property,
        "activity_type": activity_type,
        "source": source,
    }
    if shot:
        path = f"/devices/{device}/shots/{shot}/datasets"
    else:
        path = f"/devices/{device}/datasets" if device else "/datasets"
        params["shot_property"] = shot_property
    datasets, paging = await catalogue.page(path, params, offset, limit)
    return {
        "datasets": [await dataset_summary(catalogue, d) for d in datasets],
        **paging,
    }


@mcp.tool(annotations=READ_ONLY)
async def get_dataset(catalogue: CatalogueDep, id: int) -> dict[str, Any]:
    """One dataset: its description, properties and licence, each distribution
    (format, URL, and the group inside the file where one file holds several
    datasets), the Activity that produced it, and the datasets it was derived
    from. open_dataset_code gives Python that opens it.

    Args:
        id: The dataset's ID, from a search.
    """
    dataset, lineage = await asyncio.gather(
        catalogue.get(f"/datasets/{id}"), catalogue.get(f"/datasets/{id}/lineage")
    )
    record = {
        **await dataset_summary(catalogue, dataset),
        "description": dataset.get("description"),
        "license": dataset.get("license"),
        "properties": dataset.get("scientific_metadata"),
        "distributions": [
            without_empty(
                {
                    "url": distribution["url"],
                    "group": distribution.get("group"),
                    "format": distribution.get("format"),
                    "media_type": distribution.get("media_type"),
                    "endpoint_url": distribution.get("endpoint_url"),
                    "conforms_to": distribution.get("conforms_to"),
                    "default": distribution.get("default_distribution"),
                }
            )
            for distribution in dataset.get("distributions", [])
        ],
        "derived_from": lineage.get("derived_from"),
    }
    if dataset.get("activity_id"):
        activity = await catalogue.get(f"/activities/{dataset['activity_id']}")
        record["activity"] = without_empty(
            {
                **(dataset.get("activity") or {}),
                "id": activity["id"],
                "parameters": activity.get("parameters"),
                "ended_at": activity.get("ended_at"),
            }
        )
    return without_empty(record)


@mcp.tool(annotations=READ_ONLY)
async def search_collections(
    catalogue: CatalogueDep,
    device: str | None = None,
    shot: str | None = None,
    name: str | None = None,
    property: PropertyFilters = None,
    offset: Offset = 0,
    limit: Limit = 20,
) -> dict[str, Any]:
    """Find collections: named groups of datasets, such as one shot's processed
    data or the outputs of a simulation study. Returns a summary of each with
    its number of datasets; get_collection lists them.

    Args:
        device: Only this device's collections.
        shot: Only this shot's collections. Needs `device`.
        name: Only collections with this exact name.
    """
    if shot and not device:
        raise ToolError("Give `device` with `shot`: shot IDs are per device.")
    if shot:
        path = f"/devices/{device}/shots/{shot}/collections"
    else:
        path = f"/devices/{device}/collections" if device else "/collections"
    collections, paging = await catalogue.page(
        path, {"name": name, "property": property}, offset, limit
    )
    return {
        "collections": [await collection_summary(catalogue, c) for c in collections],
        **paging,
    }


@mcp.tool(annotations=READ_ONLY)
async def get_collection(catalogue: CatalogueDep, id: int) -> dict[str, Any]:
    """One collection: its description, properties, the Activity that produced
    it, the datasets in it and the collections nested inside it.

    Args:
        id: The collection's ID, from a search.
    """
    collection, (children, _) = await asyncio.gather(
        catalogue.get(f"/collections/{id}"),
        catalogue.page(f"/collections/{id}/collections", {}, 0, 50),
    )
    datasets = collection.get("datasets", [])
    return without_empty(
        {
            **await collection_summary(catalogue, collection),
            "description": collection.get("description"),
            "properties": collection.get("scientific_metadata"),
            "datasets": [await dataset_summary(catalogue, d) for d in datasets[:50]],
            "datasets_not_shown": len(datasets) - 50 if len(datasets) > 50 else None,
            "collections": [await collection_summary(catalogue, c) for c in children],
        }
    )


@mcp.tool(annotations=READ_ONLY, output_schema=None)
async def open_dataset_code(catalogue: CatalogueDep, id: int) -> str:
    """Python that opens a dataset with xarray, from its default distribution. For
    a public dataset the code carries the anonymous storage options FDS gives.
    For any other it asks FDS for short-lived credentials when it runs, with a
    token in the FDS_TOKEN environment variable. Running it needs xarray, plus
    zarr for Zarr or h5netcdf for NetCDF and HDF5, and an fsspec backend for the
    URL's scheme, such as s3fs for s3://.

    Args:
        id: The dataset's ID, from a search.
    """
    dataset = await catalogue.get(f"/datasets/{id}", {"include_storage_options": True})
    distribution = next(
        (d for d in dataset.get("distributions", []) if d.get("default_distribution")),
        None,
    )
    if distribution is None:
        raise ToolError(f"Dataset {id} has no distribution to open.")
    url = distribution["url"]
    imports, opening = opener_for(distribution)
    if dataset.get("effective_access_level") == "public":
        options = dataset.get("storage_options")
        if options is None:
            raise ToolError(
                f"FDS gave no storage options for dataset {id}, whose data is at "
                f"{url}: open it with the tools for that store."
            )
        credentials = [f"storage_options = {options!r}"]
    else:
        imports += ["import os", "import requests"]
        credentials_url = f"{catalogue.api}/file-access/credentials"
        credentials = [
            "response = requests.post(",
            f"    {credentials_url!r},",
            '    params={"include_storage_options": "true"},',
            '    json={"data_urls": [url]},',
            '    headers={"Authorization": f"Bearer {os.environ[\'FDS_TOKEN\']}"},',
            ")",
            "response.raise_for_status()",
            'storage_options = response.json()["resource_map"][url]["storage_options"]',
        ]
    return "\n".join([*sorted(imports), "", f"url = {url!r}", *credentials, *opening])


def opener_for(distribution: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The imports and the statements that open a distribution with xarray, once
    `url` and `storage_options` are set."""
    media_type = distribution.get("media_type") or ""
    if "zarr" in media_type:
        return (
            ["import xarray as xr"],
            ["ds = xr.open_zarr(url, storage_options=storage_options)"],
        )
    if "netcdf" in media_type or "hdf5" in media_type:
        group = distribution.get("group")
        return (
            ["import fsspec", "import xarray as xr"],
            [
                "f = fsspec.open(url, **storage_options).open()",
                f'ds = xr.open_dataset(f, engine="h5netcdf", group={group!r})',
            ],
        )
    raise ToolError(
        f"No opener is known for media type {media_type or 'unset'!r}; the data "
        f"is at {distribution['url']}."
    )


async def shot_summary(
    catalogue: Catalogue, shot: dict[str, Any], full: bool = False
) -> dict[str, Any]:
    """A shot as the tools return it. Listings leave out the properties'
    descriptions; `full` keeps them."""
    device, shot_id = shot["device_name"], shot["id"]
    properties = shot.get("scientific_metadata", [])
    return without_empty(
        {
            "device": device,
            "shot": shot_id,
            "shot_at": shot.get("shot_at"),
            "access_level": shot.get("effective_access_level"),
            "properties": properties if full else without_descriptions(properties),
            "link": await catalogue.landing_page(f"/devices/{device}/shots/{shot_id}"),
        }
    )


async def dataset_summary(
    catalogue: Catalogue, dataset: dict[str, Any]
) -> dict[str, Any]:
    return without_empty(
        {
            "id": dataset["id"],
            "name": dataset["name"],
            "title": dataset.get("title"),
            "device": dataset.get("device_name"),
            "shot": dataset.get("shot_id"),
            "access_level": dataset.get("effective_access_level"),
            "activity": dataset.get("activity"),
            "formats": [
                d.get("format") or d.get("media_type")
                for d in dataset.get("distributions", [])
            ],
            "link": await catalogue.landing_page(f"/datasets/{dataset['id']}"),
        }
    )


async def collection_summary(
    catalogue: Catalogue, collection: dict[str, Any]
) -> dict[str, Any]:
    return without_empty(
        {
            "id": collection["id"],
            "name": collection["name"],
            "title": collection.get("title"),
            "device": collection.get("device_name"),
            "shot": collection.get("shot_id"),
            "access_level": collection.get("effective_access_level"),
            "activity": collection.get("activity"),
            "dataset_count": len(collection.get("datasets", [])),
            "link": await catalogue.landing_page(f"/collections/{collection['id']}"),
        }
    )


def without_descriptions(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Properties without their descriptions and kinds, which would repeat on
    every record of a listing. A group's properties are trimmed the same way."""
    return [
        {
            key: without_descriptions(value) if key == "properties" else value
            for key, value in entry.items()
            if key not in ("description", "kind")
        }
        for entry in properties
    ]


@mcp.resource("fds://devices", mime_type="application/json")
async def devices_resource(catalogue: CatalogueDep) -> dict[str, Any]:
    """The devices this catalogue holds records for."""
    return await list_devices(catalogue)


@mcp.resource("fds://shots/{device}/{shot}", mime_type="application/json")
async def shot_resource(
    catalogue: CatalogueDep, device: str, shot: str
) -> dict[str, Any]:
    """One shot's record: its properties, datasets and collections."""
    return await get_shot(catalogue, device, shot)


@mcp.resource("fds://datasets/{id}", mime_type="application/json")
async def dataset_resource(catalogue: CatalogueDep, id: int) -> dict[str, Any]:
    """One dataset's record: its distributions, the Activity behind it and the
    datasets it was derived from."""
    return await get_dataset(catalogue, id)


@mcp.resource("fds://collections/{id}", mime_type="application/json")
async def collection_resource(catalogue: CatalogueDep, id: int) -> dict[str, Any]:
    """One collection's record: its datasets and the collections inside it."""
    return await get_collection(catalogue, id)


@mcp.prompt
def find_shots(device: str) -> str:
    """Find the shots that answer a question, and list them in a table. Type the
    question after the device: Claude Code passes one word per argument, so the
    question cannot be an argument of its own.

    Args:
        device: The device's name, such as `mast`.
    """
    return f"""Find the {device} shots that answer my question. My question is
whatever I typed after this command. If I typed nothing after it, ask me what
I am looking for before you search.

Work like this:
1. Call describe_shot_properties for {device} to see which properties exist,
   their values and their units.
2. Turn the question into filters on those properties, converting any values
   into the units the summary gives.
3. Call search_shots with those filters, and fetch every page.

Answer with a table of the shots found: each shot's ID as a link to its record,
its time, and the properties the question asks about. Below the table, give the
filters you used. If no shot matches, say so, and give the filters you tried."""


@mcp.prompt
async def explain_dataset(catalogue: CatalogueDep, id: int) -> list[Message]:
    """Explain a dataset: what it holds, what produced it, and how to open it.

    Args:
        id: The dataset's ID, such as `53`.
    """
    record = await get_dataset(catalogue, id)
    return [
        Message(
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=f"fds://datasets/{id}",
                    mime_type="application/json",
                    text=json.dumps(record),
                ),
            )
        ),
        Message(
            "Explain this dataset to me in plain words: what it holds, which "
            "Activity produced it and when, which formats it is stored in, and "
            "how I would open it in Python (call open_dataset_code for the code)."
        ),
    ]


@mcp.completion
async def suggest(
    ref: PromptReference | ResourceTemplateReference,
    argument: CompletionArgument,
    context: CompletionContext | None,
) -> list[str] | None:
    """Values to offer while someone types an address or a prompt's arguments."""
    already_given = (context.arguments or {}) if context else {}
    catalogue = catalogue_for_caller(get_context())
    return await suggestions(catalogue, ref, argument, already_given)


async def suggestions(
    catalogue: Catalogue,
    ref: PromptReference | ResourceTemplateReference,
    argument: CompletionArgument,
    already_given: dict[str, str],
) -> list[str] | None:
    """Device names for any argument called `device`, in a shot's address or in
    a prompt. For a shot's address, then the IDs of that device's shots that
    start with what has been typed for `{shot}`."""
    if argument.name == "device":
        devices = await catalogue.get("/devices/")
        return [d["name"] for d in devices if d["name"].startswith(argument.value)]
    is_shot_address = (
        isinstance(ref, ResourceTemplateReference)
        and ref.uri == "fds://shots/{device}/{shot}"
    )
    device = already_given.get("device")
    if is_shot_address and argument.name == "shot" and device:
        shots, _ = await catalogue.page(
            f"/devices/{device}/shots", {"id_prefix": argument.value or None}, 0, 50
        )
        return [shot["id"] for shot in shots]
    return None
