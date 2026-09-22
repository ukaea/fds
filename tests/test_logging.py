import json
import logging

import structlog

from app.core.logging import mark_logged


class TestRedaction:
    def test_structlog_keys_are_redacted(self, log_lines):
        structlog.get_logger("test").info(
            "vend",
            session_token="super-secret",
            aws_secret_access_key="also-secret",
            dataset_id=7,
        )

        (line,) = log_lines()
        assert line["session_token"] == "[redacted]"
        assert line["aws_secret_access_key"] == "[redacted]"
        assert line["dataset_id"] == 7

    def test_nested_keys_are_redacted(self, log_lines):
        structlog.get_logger("test").info(
            "vend", payload={"url": "s3://bucket/key", "credentials": {"key": "abc"}}
        )

        (line,) = log_lines()
        assert line["payload"]["credentials"] == "[redacted]"
        assert line["payload"]["url"] == "s3://bucket/key"

    def test_foreign_records_are_redacted_too(self, log_lines):
        """A library logging through the stdlib must not bypass redaction.

        This is what ``foreign_pre_chain`` buys, and the reason redaction can
        be described as covering the process rather than covering our own
        call sites.
        """
        logging.getLogger("uvicorn.error").warning(
            "handshake failed", extra={"authorization": "Bearer abc123"}
        )

        (line,) = log_lines()
        assert line["authorization"] == "[redacted]"
        assert "abc123" not in json.dumps(line)


class TestForeignLoggers:
    def test_uvicorn_records_are_json(self, log_lines):
        """Uvicorn sets propagate=False, so this only works if it is named."""
        logging.getLogger("uvicorn.error").info("Application startup complete")

        (line,) = log_lines()
        assert line["event"] == "Application startup complete"
        assert line["logger"] == "uvicorn.error"
        assert line["level"] == "info"

    def test_access_log_is_dropped(self, log_lines):
        """The per-request audit line replaces it, and duplicates are noise."""
        logging.getLogger("uvicorn.access").info("GET /v1/datasets 200 OK")

        assert log_lines() == []


class TestReservedKeys:
    def test_name_is_usable_as_a_field(self, log_lines):
        """``name`` is the natural key on most FDS models.

        The stdlib's ``extra=`` refuses it, because ``LogRecord`` already has
        an attribute of that name. Emitting an audit line for a rename must
        not raise.
        """
        structlog.get_logger("fds.audit").info(
            "dataset.update", name="ip_thomson", module="core", args=[1, 2]
        )

        (line,) = log_lines()
        assert line["name"] == "ip_thomson"
        assert line["module"] == "core"
        assert line["args"] == [1, 2]


class TestNoise:
    def test_uvicorn_colour_duplicate_is_dropped(self, log_lines):
        """color_message is the same message again, wrapped in ANSI escapes."""
        logging.getLogger("uvicorn.error").info(
            "Started server process [1]",
            extra={"color_message": "Started server process [\x1b[36m%d\x1b[0m]"},
        )

        (line,) = log_lines()
        assert "color_message" not in line
        assert line["event"] == "Started server process [1]"


class TestDuplicateTracebacks:
    def test_server_copy_of_a_logged_exception_is_dropped(self, log_lines):
        """Starlette re-raises after our handler runs, so uvicorn logs it again."""
        err = RuntimeError("kaboom")
        try:
            raise err
        except RuntimeError as exc:
            structlog.get_logger("app.probe").error("request.failed", exc_info=exc)
            mark_logged(exc)
            logging.getLogger("uvicorn.error").error("Exception in ASGI", exc_info=exc)

        (line,) = log_lines()
        assert line["event"] == "request.failed"

    def test_unlogged_server_exception_still_gets_through(self, log_lines):
        try:
            raise ValueError("unhandled")
        except ValueError as exc:
            logging.getLogger("uvicorn.error").error("Exception in ASGI", exc_info=exc)

        (line,) = log_lines()
        assert line["event"] == "Exception in ASGI"
