import logging
import logging.config
import sys
from typing import Any

import structlog
from opentelemetry import trace

from app.core.config import config
from app.core.context import get_actor

SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
)

REDACTED = "[redacted]"


def mark_logged(exc: BaseException) -> None:
    """Note that this exception's traceback is already in the log."""
    setattr(exc, "_fds_logged", True)


class DropAlreadyLogged(logging.Filter):
    """Drop a traceback the application has already recorded.

    Starlette re-raises after an exception handler returns, by design, so the
    ASGI server logs the same exception a second time without the actor, path
    or trace id ours carries.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not getattr(exc, "_fds_logged", False)


def add_actor(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Attach the requesting user to every line logged during a request."""
    actor = get_actor()
    if actor is not None:
        event_dict["actor_id"] = actor.id
        event_dict["actor_issuer"] = actor.issuer
    return event_dict


def add_trace_context(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Attach the active span's ids, so logs and traces can be joined."""
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = trace.format_trace_id(span_context.trace_id)
        event_dict["span_id"] = trace.format_span_id(span_context.span_id)
    return event_dict


def drop_noise(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Drop uvicorn's ``color_message``, an ANSI copy of the message itself."""
    event_dict.pop("color_message", None)
    return event_dict


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive(str(key)) else _redact(inner)
            for key, inner in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def redact_sensitive(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace the value of any sensitive-looking key, at any depth."""
    return _redact(event_dict)


def _use_json() -> bool:
    configured = config.LOG_FORMAT.lower()
    if configured in ("json", "console"):
        return configured == "json"
    return config.ENVIRONMENT.lower() in ("production", "prod")


def _build_formatter() -> logging.Formatter:
    """The one formatter, shared by every handler."""
    use_json = _use_json()
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if use_json
        # Plain tracebacks: rich reprints source around every frame, turning
        # one failed request into thousands of lines of terminal.
        else structlog.dev.ConsoleRenderer(
            exception_formatter=structlog.dev.plain_traceback
        )
    )

    # ConsoleRenderer formats exceptions itself, and does it better.
    render_chain: list[Any] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta
    ]
    if use_json:
        render_chain.append(structlog.processors.format_exc_info)
    render_chain.append(renderer)

    return structlog.stdlib.ProcessorFormatter(
        # Library records arrive as bare LogRecords; ours have already been
        # through the chain by this point.
        foreign_pre_chain=[structlog.stdlib.ExtraAdder(), *shared_processors()],
        processors=render_chain,
    )


def shared_processors() -> list[Any]:
    """Processors applied to every record, from any source."""
    return [
        add_actor,
        add_trace_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        drop_noise,
        redact_sensitive,
    ]


def setup_logging() -> None:
    """Route every logger in the process into one structured stream."""
    structlog.configure(
        processors=[
            *shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    level = (config.LOG_LEVEL or "INFO").upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"fds": {"()": _build_formatter}},
            "filters": {"drop_already_logged": {"()": DropAlreadyLogged}},
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "fds",
                },
                "null": {"class": "logging.NullHandler"},
            },
            "root": {"handlers": ["default"], "level": level},
            "loggers": {
                # Uvicorn gives `uvicorn` its own handler and propagate=False,
                # so nothing in its subtree reaches root on its own.
                "uvicorn": {
                    "handlers": ["default"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["default"],
                    "filters": ["drop_already_logged"],
                    "level": level,
                    "propagate": False,
                },
                # Dropped, not reformatted: the fds.audit line already covers
                # every request, and names the actor too.
                "uvicorn.access": {
                    "handlers": ["null"],
                    "level": level,
                    "propagate": False,
                },
                # Named only to pin the level; chatty at INFO.
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )
