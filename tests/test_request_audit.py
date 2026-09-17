import pytest
from fastapi.testclient import TestClient

from app.api.middleware import route_template
from app.auth.security import _hash_user_id
from app.main import app

TEST_ISSUER = "https://test-idp.com"


def audit_lines(lines: list[dict]) -> list[dict]:
    return [line for line in lines if line.get("logger") == "fds.audit"]


class TestRequestLine:
    def test_one_line_per_request(self, test_client, log_lines):
        test_client.get("/api/v1/devices/")

        assert len(audit_lines(log_lines())) == 1

    def test_line_describes_the_request(self, test_client, log_lines):
        response = test_client.get("/api/v1/devices/")
        assert response.status_code == 200

        (line,) = audit_lines(log_lines())
        assert line["event"] == "request"
        assert line["method"] == "GET"
        assert line["status"] == 200
        assert line["path"] == "/api/v1/devices/"

    def test_route_is_the_template_not_the_path(self, test_client, log_lines):
        """Templates are what make lines groupable across ids."""
        test_client.get("/api/v1/devices/mast")

        (line,) = audit_lines(log_lines())
        assert line["route"] == "/api/v1/devices/{device_name}"
        assert line["path"] == "/api/v1/devices/mast"

    def test_failed_request_still_logged(self, test_client, log_lines):
        response = test_client.get("/api/v1/devices/nonexistent")
        assert response.status_code == 404

        (line,) = audit_lines(log_lines())
        assert line["status"] == 404

    def test_health_is_not_audited(self, test_client, log_lines):
        """A probe every few seconds would otherwise drown the trail."""
        assert test_client.get("/health").status_code == 200

        assert audit_lines(log_lines()) == []


class TestActor:
    def test_authenticated_request_names_the_actor(
        self, test_client, admin_user_token, log_lines
    ):
        test_client.get("/api/v1/devices/", headers=admin_user_token)

        (line,) = audit_lines(log_lines())
        assert line["actor_id"] == _hash_user_id(TEST_ISSUER, "test-admin-user")
        assert line["actor_issuer"] == TEST_ISSUER

    def test_actor_is_pseudonymous(self, test_client, admin_user_token, log_lines):
        """The subject claim itself must never reach the log."""
        test_client.get("/api/v1/devices/", headers=admin_user_token)

        (line,) = audit_lines(log_lines())
        assert "test-admin-user" not in str(line)
        assert len(line["actor_id"]) == 64

    def test_anonymous_request_is_marked(self, test_client, log_lines):
        test_client.get("/api/v1/devices/")

        (line,) = audit_lines(log_lines())
        assert line["actor_id"] == "anonymous"


class TestDenials:
    def test_denial_is_logged_as_a_warning(
        self, test_client, non_admin_user_token, log_lines
    ):
        response = test_client.post(
            "/api/v1/devices/",
            json={"name": "mast"},
            headers=non_admin_user_token,
        )
        assert response.status_code == 403

        lines = log_lines()
        (denial,) = [line for line in lines if line["event"] == "access.denied"]
        assert denial["level"] == "warning"
        assert denial["method"] == "POST"
        assert denial["path"] == "/api/v1/devices/"
        assert denial["actor_id"] == _hash_user_id(TEST_ISSUER, "test-non-admin-user")
        assert denial["detail"]

    def test_denial_and_request_line_share_the_actor(
        self, test_client, non_admin_user_token, log_lines
    ):
        """Every line in a request is attributable, not just the audit one."""
        test_client.post(
            "/api/v1/devices/", json={"name": "mast"}, headers=non_admin_user_token
        )

        lines = log_lines()
        actors = {line["actor_id"] for line in lines if "actor_id" in line}
        assert len(actors) == 1


class TestUnhandledErrors:
    """The catch-all handler: nothing may fail silently."""

    @pytest.fixture(scope="class", autouse=True)
    def boom_route(self):
        @app.get("/__boom", include_in_schema=False)
        def boom() -> None:
            raise RuntimeError("kaboom")

        yield
        app.router.routes = [
            route
            for route in app.router.routes
            if getattr(route, "path", None) != "/__boom"
        ]

    def test_unhandled_error_is_logged_with_traceback(self, log_lines):
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/__boom")
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

        lines = log_lines()
        (failure,) = [line for line in lines if line["event"] == "request.failed"]
        assert failure["level"] == "error"
        assert failure["error_type"] == "RuntimeError"
        assert "kaboom" in failure["exception"]

    def test_failed_request_still_produces_an_audit_line(self, log_lines):
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/__boom")

        (line,) = audit_lines(log_lines())
        assert line["status"] == 500


class TestTraceCorrelation:
    """Logs and traces are joined by trace_id, so every line needs one."""

    def test_lines_carry_a_trace_id(self, test_client, log_lines):
        pytest.importorskip("opentelemetry.sdk")

        test_client.get("/api/v1/devices/")

        (line,) = audit_lines(log_lines())
        assert line.get("trace_id"), (
            "no trace_id on the audit line; tracing may not be installed"
        )
        assert len(line["trace_id"]) == 32

    def test_all_lines_in_a_request_share_a_trace_id(
        self, test_client, non_admin_user_token, log_lines
    ):
        pytest.importorskip("opentelemetry.sdk")

        test_client.post(
            "/api/v1/devices/", json={"name": "mast"}, headers=non_admin_user_token
        )

        trace_ids = {line["trace_id"] for line in log_lines() if line.get("trace_id")}
        assert len(trace_ids) == 1


class TestRouteTemplate:
    """The prefix has to be rebuilt from the concrete path, so the cases that
    matter are the ones where a naive substitution would go wrong."""

    @staticmethod
    def _scope(path: str, tail: str, params: dict[str, str]) -> dict:
        class Route:
            def __init__(self, p: str) -> None:
                self.path = p

        return {"path": path, "route": Route(tail), "path_params": params}

    def test_nested_prefixes_with_a_repeated_value(self):
        # "mast" is both the device (in the prefix) and the dataset name (in the
        # tail). Anchoring on the tail keeps each substitution in its own place.
        scope = self._scope(
            "/api/v1/devices/mast/shots/30420/datasets/mast",
            "/{shot}/datasets/{name}",
            {"device": "mast", "shot": "30420", "name": "mast"},
        )
        assert route_template(scope) == (
            "/api/v1/devices/{device}/shots/{shot}/datasets/{name}"
        )

    def test_value_that_matches_a_literal_prefix_segment(self):
        # A device literally called "devices" must not turn the fixed segment
        # into a placeholder.
        scope = self._scope(
            "/api/v1/devices/devices/shots/1",
            "/{shot}",
            {"device_name": "devices", "shot": "1"},
        )
        assert route_template(scope) == "/api/v1/devices/{device_name}/shots/{shot}"

    def test_two_prefix_parameters_sharing_a_value(self):
        # Right-to-left pairing keeps each placeholder at its own position even
        # when the values are identical.
        scope = self._scope(
            "/a/x/b/x/tail",
            "/tail",
            {"first": "x", "second": "x"},
        )
        assert route_template(scope) == "/a/{first}/b/{second}/tail"

    def test_no_route_falls_back_to_the_path(self):
        assert route_template({"path": "/nowhere"}) == "/nowhere"
