import json
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.utilities.asgi_transport import StreamingASGITransport, run_asgi_lifespan
from mcp_types import (
    CompletionArgument,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    EmbeddedResource,
    ResourceTemplateReference,
    TextContent,
    TextResourceContents,
    ToolAnnotations,
)
from sqlmodel import Session

from fds.auth.security import AuthenticatedUser
from fds.main import app
from fds.mcp.catalogue import Catalogue
from fds.mcp.server import (
    ask_for_device,
    device_chosen,
    explain_dataset,
    get_shot,
    mcp,
    open_dataset_code,
    search_datasets,
    search_shots,
    suggestions,
)
from fds.models.dataset import DatasetCreate
from fds.models.device import DeviceCreate
from fds.models.policy import AccessLevel
from fds.models.shot import ShotCreate
from fds.services.dataset_service import DatasetService
from fds.services.device_service import DeviceService
from fds.services.shot_service import ShotService


class FakeFDS(httpx.AsyncBaseTransport):
    """Answers each path with the status and body given for it, 404 for any
    other, and keeps the requests it was sent."""

    def __init__(self, answers: dict[str, tuple[int, Any]]):
        self.answers = answers
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.answers.get(
            request.url.path, (404, {"detail": "Not Found"})
        )
        return httpx.Response(status, json=body)


def catalogue_on(
    fds: httpx.AsyncBaseTransport, authorization: str | None = None
) -> Catalogue:
    http = httpx.AsyncClient(transport=fds)
    return Catalogue(http, api="http://fds.test/v1", authorization=authorization)


def through_fds(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
    **settings: Any,
) -> httpx.AsyncClient:
    """An HTTP client whose requests go to this process's app, for an MCP client."""
    return httpx.AsyncClient(
        transport=StreamingASGITransport(app),
        headers=headers,
        timeout=timeout,
        auth=auth,
        **settings,
    )


def mcp_client(token: str | None = None) -> Client:
    """A client of the MCP server at FDS's /mcp, calling this process's app."""
    return Client(
        StreamableHttpTransport(
            url="http://fds.example.org/mcp",
            auth=token,
            httpx_client_factory=through_fds,
        )
    )


def shot(shot_id: str) -> dict[str, Any]:
    return {
        "id": shot_id,
        "device_name": "mast",
        "shot_at": "2013-09-27T15:20:00Z",
        "effective_access_level": "public",
        "scientific_metadata": [
            {
                "name": "plasma_current_max",
                "value": 601164.7,
                "unit": "A",
                "kind": "quantity",
                "description": "Maximum plasma current during the shot.",
            }
        ],
    }


async def test_the_model_sees_parameters_but_not_the_catalogue():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    schema = tools["search_shots"].input_schema
    assert "catalogue" not in schema["properties"]
    assert "ctx" not in schema["properties"]
    assert "required" not in schema
    assert "confinement_mode:H-mode" in schema["properties"]["property"]["description"]
    assert schema["properties"]["device"]["description"].startswith(
        "The device's name, such as `mast`. Leave it out"
    )
    assert tools["search_shots"].annotations == ToolAnnotations(read_only_hint=True)


async def test_the_model_reads_dataset_code_as_plain_text():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    assert tools["open_dataset_code"].output_schema is None


async def test_the_model_sees_the_activity_types_it_can_pick():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    activity_type = tools["search_datasets"].input_schema["properties"]["activity_type"]
    assert activity_type["anyOf"][0]["enum"] == [
        "measurement",
        "analysis",
        "simulation",
        "calibration",
    ]


async def test_search_shots_sends_the_filters():
    fds = FakeFDS({"/v1/devices/mast/shots": (200, [])})

    await search_shots(
        catalogue_on(fds),
        device="mast",
        property=["confinement_mode:H-mode", "elm"],
        property_min=["plasma_current_max:700000"],
    )

    params = fds.requests[0].url.params
    assert params.get_list("property") == ["confinement_mode:H-mode", "elm"]
    assert params.get_list("property_min") == ["plasma_current_max:700000"]
    assert "property_max" not in params
    assert "id_prefix" not in params


async def test_search_shots_gives_the_next_offset_when_there_are_more():
    shots = [shot(str(30400 + n)) for n in range(4)]
    fds = FakeFDS({"/v1/devices/mast/shots": (200, shots)})

    result = await search_shots(catalogue_on(fds), device="mast", offset=6, limit=3)
    assert isinstance(result, dict)

    assert fds.requests[0].url.params["offset"] == "6"
    assert fds.requests[0].url.params["limit"] == "4"
    assert [s["shot"] for s in result["shots"]] == ["30400", "30401", "30402"]
    assert result["next_offset"] == 9


async def test_search_shots_gives_no_next_offset_on_the_last_page():
    fds = FakeFDS({"/v1/devices/mast/shots": (200, [shot("30420")])})

    result = await search_shots(catalogue_on(fds), device="mast", limit=3)
    assert isinstance(result, dict)

    assert result["returned"] == 1
    assert "next_offset" not in result


async def test_an_empty_search_still_says_which_device_it_searched():
    fds = FakeFDS({"/v1/devices/mastu/shots": (200, [])})

    result = await search_shots(catalogue_on(fds), device="mastu")

    assert result == {"device": "mastu", "shots": [], "offset": 0, "returned": 0}


async def test_search_shots_leaves_out_property_descriptions():
    fds = FakeFDS({"/v1/devices/mast/shots": (200, [shot("30420")])})

    result = await search_shots(catalogue_on(fds), device="mast")
    assert isinstance(result, dict)

    assert result["shots"][0]["properties"] == [
        {"name": "plasma_current_max", "value": 601164.7, "unit": "A"}
    ]


async def test_records_link_to_their_landing_page():
    fds = FakeFDS(
        {
            "/v1/devices/mast/shots": (200, [shot("30420")]),
            "/v1/catalog": (200, {"@id": "https://fds.example.org/catalog"}),
        }
    )

    result = await search_shots(catalogue_on(fds), device="mast")
    assert isinstance(result, dict)

    assert result["shots"][0]["link"] == (
        "https://fds.example.org/devices/mast/shots/30420"
    )


async def test_requests_carry_the_callers_token():
    fds = FakeFDS({"/v1/devices/mast/shots": (200, [])})

    await search_shots(catalogue_on(fds, "Bearer abc"), device="mast")

    assert fds.requests[0].headers["authorization"] == "Bearer abc"


async def test_refusal_without_a_token_says_only_public_records_can_be_read():
    fds = FakeFDS({"/v1/devices/mast/shots": (403, {"detail": "Not authorised"})})

    with pytest.raises(ToolError, match="only public records can be read"):
        await search_shots(catalogue_on(fds), device="mast")


async def test_an_error_inside_fds_is_reported_with_its_status():
    fds = FakeFDS({"/v1/devices/mast/shots": (500, {"detail": "Internal error"})})

    with pytest.raises(ToolError, match="FDS answered 500: Internal error"):
        await search_shots(catalogue_on(fds), device="mast")


async def test_get_shot_lists_its_datasets_and_collections():
    fds = FakeFDS(
        {
            "/v1/devices/mast/shots/30420": (200, shot("30420")),
            "/v1/devices/mast/shots/30420/datasets": (
                200,
                [{"id": 1, "name": "equilibrium", "shot_id": "30420"}],
            ),
            "/v1/devices/mast/shots/30420/collections": (
                200,
                [{"id": 6, "name": "jintrac-v220922", "datasets": [{}, {}, {}]}],
            ),
        }
    )

    result = await get_shot(catalogue_on(fds), device="mast", shot="30420")

    assert result["properties"][0]["description"] == (
        "Maximum plasma current during the shot."
    )
    assert [d["name"] for d in result["datasets"]] == ["equilibrium"]
    assert result["collections"][0]["dataset_count"] == 3
    assert result["more_datasets"] is False


async def test_get_shot_reports_a_shot_that_does_not_exist():
    fds = FakeFDS(
        {"/v1/devices/mast/shots/99999": (404, {"detail": "Shot '99999' not found"})}
    )

    with pytest.raises(ToolError, match="Not found: Shot '99999' not found"):
        await get_shot(catalogue_on(fds), device="mast", shot="99999")


async def test_search_datasets_on_a_shot_needs_the_device():
    fds = FakeFDS({})

    with pytest.raises(ToolError, match="Give `device`"):
        await search_datasets(catalogue_on(fds), shot="30420")
    assert fds.requests == []


async def test_open_dataset_code_for_public_data_carries_the_storage_options():
    dataset = {
        "id": 51,
        "effective_access_level": "public",
        "storage_options": {"anon": True},
        "distributions": [
            {
                "url": "s3://mast/level2/shots/29974.zarr/bolometer",
                "media_type": "application/x-zarr",
                "default_distribution": True,
            }
        ],
    }
    fds = FakeFDS({"/v1/datasets/51": (200, dataset)})

    code = await open_dataset_code(catalogue_on(fds), id=51)

    assert "storage_options = {'anon': True}" in code
    assert "xr.open_zarr(url, storage_options=storage_options)" in code
    assert "FDS_TOKEN" not in code


async def test_open_dataset_code_for_restricted_data_asks_for_credentials():
    dataset = {
        "id": 7,
        "effective_access_level": "restricted",
        "distributions": [
            {
                "url": "s3://bucket/shots/30421.nc",
                "group": "equilibrium",
                "media_type": "application/x-netcdf",
                "default_distribution": True,
            }
        ],
    }
    fds = FakeFDS({"/v1/datasets/7": (200, dataset)})

    code = await open_dataset_code(catalogue_on(fds, "Bearer abc"), id=7)

    assert "'http://fds.test/v1/file-access/credentials'" in code
    assert "os.environ['FDS_TOKEN']" in code
    assert "xr.open_dataset(f, engine=\"h5netcdf\", group='equilibrium')" in code
    compile(code, "generated", "exec")


async def test_records_have_addresses_a_client_can_read():
    async with Client(mcp) as client:
        resources = [str(r.uri) for r in await client.list_resources()]
        templates = [t.uri_template for t in await client.list_resource_templates()]

    assert resources == ["fds://devices"]
    assert templates == [
        "fds://shots/{device}/{shot}",
        "fds://datasets/{id}",
        "fds://collections/{id}",
    ]


async def test_typing_a_shot_address_suggests_that_devices_shots():
    fds = FakeFDS({"/v1/devices/mast/shots": (200, [shot("30420"), shot("30421")])})
    ref = ResourceTemplateReference(
        type="ref/resource", uri="fds://shots/{device}/{shot}"
    )

    values = await suggestions(
        catalogue_on(fds),
        ref,
        CompletionArgument(name="shot", value="304"),
        {"device": "mast"},
    )

    assert values == ["30420", "30421"]
    assert fds.requests[0].url.params["id_prefix"] == "304"


async def test_prompts_ask_only_for_what_a_person_types():
    async with Client(mcp) as client:
        prompts = {p.name: p for p in await client.list_prompts()}

    assert [a.name for a in prompts["find_shots"].arguments or []] == ["device"]
    assert [a.name for a in prompts["explain_dataset"].arguments or []] == ["id"]


async def test_explain_dataset_brings_the_record_with_it():
    dataset = {"id": 53, "name": "equilibrium", "distributions": []}
    fds = FakeFDS(
        {
            "/v1/datasets/53": (200, dataset),
            "/v1/datasets/53/lineage": (200, {"derived_from": []}),
        }
    )

    messages = await explain_dataset(catalogue_on(fds), id=53)

    record = messages[0].content
    assert isinstance(record, EmbeddedResource)
    assert isinstance(record.resource, TextResourceContents)
    assert record.resource.uri == "fds://datasets/53"
    assert '"name": "equilibrium"' in record.resource.text


async def test_shot_search_uses_the_only_device_when_none_is_given():
    fds = FakeFDS(
        {
            "/v1/devices/": (200, [{"name": "mast"}]),
            "/v1/devices/mast/shots": (200, [shot("30420")]),
        }
    )

    result = await search_shots(catalogue_on(fds))

    assert isinstance(result, dict)
    assert result["device"] == "mast"
    assert "device_chosen_by_user" not in result
    assert result["shots"][0]["shot"] == "30420"


async def test_shot_search_without_a_way_to_ask_needs_the_device():
    fds = FakeFDS({"/v1/devices/": (200, [{"name": "mast"}, {"name": "mastu"}])})

    with pytest.raises(ToolError, match="this catalogue holds mast, mastu"):
        await search_shots(catalogue_on(fds))


def test_the_question_about_the_device_offers_each_device():
    devices = [
        {"name": "mast", "title": "MAST"},
        {"name": "mastu", "title": "MAST Upgrade"},
    ]

    question = ask_for_device(devices).input_requests or {}

    request = question["device"]
    assert isinstance(request, ElicitRequest)
    assert isinstance(request.params, ElicitRequestFormParams)
    field = request.params.requested_schema["properties"]["device"]
    assert field["title"] == "Device"
    assert field["oneOf"] == [
        {"const": "mast", "title": "MAST"},
        {"const": "mastu", "title": "MAST Upgrade"},
    ]


def test_a_device_the_user_picks_is_used():
    assert device_chosen(
        ElicitResult(action="accept", content={"device": "mastu"})
    ) == ("mastu")


def test_declining_to_pick_a_device_tells_the_model_to_ask():
    with pytest.raises(ToolError, match="Ask them which device"):
        device_chosen(ElicitResult(action="decline"))


@pytest.mark.usefixtures("test_client")
async def test_the_server_at_mcp_reads_the_catalogue(
    session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    session.commit()

    async with run_asgi_lifespan(app), mcp_client() as client:
        result = await client.call_tool("list_devices", {})

    assert [d["name"] for d in result.data["devices"]] == ["mast"]


@pytest.mark.usefixtures("test_client")
async def test_the_server_at_mcp_reads_with_the_token_sent_to_it(
    session: Session,
    admin_user: AuthenticatedUser,
    mock_jwks_client,
    mock_jwt_decode,
    monkeypatch,
):
    DeviceService(session).create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(device_name="JET", id="200", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    session.commit()
    monkeypatch.setattr("fds.auth.jwks._jwks_client_instance", mock_jwks_client)
    mock_jwt_decode.return_value = {
        "sub": "test-admin-user",
        "scp": "fds-admin",
        "iss": "https://test-idp.com",
    }

    async with run_asgi_lifespan(app):
        async with mcp_client() as client:
            anonymous = await client.call_tool("search_shots", {"device": "JET"})
        async with mcp_client("admin-token") as client:
            admin = await client.call_tool("search_shots", {"device": "JET"})

    assert anonymous.data["shots"] == []
    assert "not_signed_in" in anonymous.data
    assert [s["shot"] for s in admin.data["shots"]] == ["200"]
    assert "not_signed_in" not in admin.data
    assert mock_jwt_decode.call_args.args[0] == "admin-token"


@pytest.mark.usefixtures("test_client")
async def test_results_read_without_a_token_say_where_to_log_in(
    session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    session.commit()

    async with run_asgi_lifespan(app), mcp_client() as client:
        result = await client.call_tool("list_devices", {})
        record = await client.read_resource("fds://devices")

    metadata = "http://fds.example.org/.well-known/oauth-protected-resource/mcp"
    assert "public records only" in result.data["not_signed_in"]
    assert metadata in result.data["not_signed_in"]
    (contents,) = record
    assert isinstance(contents, TextResourceContents)
    assert metadata in json.loads(contents.text)["not_signed_in"]


def test_the_server_at_mcp_refuses_a_token_fds_would_refuse(test_client: TestClient):
    response = test_client.post(
        "/mcp",
        headers={"Authorization": "Bearer not-a-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == (
        'Bearer error="invalid_token", resource_metadata='
        '"http://testserver/.well-known/oauth-protected-resource/mcp"'
    )


@pytest.mark.usefixtures("admin_user_token", "test_client")
async def test_dataset_code_from_mcp_asks_for_credentials_where_the_client_called(
    session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="core_temp",
            url="s3://bucket/core_temp.nc",
            media_type="application/x-netcdf",
            device_name="JET",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    session.commit()

    async with run_asgi_lifespan(app), mcp_client() as client:
        result = await client.call_tool("open_dataset_code", {"id": dataset.id})

    code = result.content[0]
    assert isinstance(code, TextContent)
    assert "'http://fds.example.org/v1/file-access/credentials'" in code.text
