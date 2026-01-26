import logging
import sys
from typing import Any

from pythonjsonlogger import json

from app.core.config import config


class CustomJsonFormatter(json.JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        if not log_record.get("timestamp"):
            # Use ISO8601 format
            log_record["timestamp"] = self.formatTime(record, self.datefmt)
        if log_record.get("level"):
            log_record["level"] = log_record["level"].upper()
        else:
            log_record["level"] = record.levelname


def setup_logging() -> None:
    """
    Configures the root logger to use JSON formatting.
    """
    # Create a handler depending on the environment
    handler = logging.StreamHandler(sys.stdout)

    # Use JSON formatting for production-like environments
    if getattr(config, "ENVIRONMENT", "dev").lower() in ("production", "prod"):
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        )
    else:
        # Development: simpler format, possibly just standard logging or pretty-printed JSON
        # For consistency with the requirement "Structured JSON Logging", we stick to JSON
        # but usage of different formatters is enabled here.
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        )

    handler.setFormatter(formatter)

    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]

    # Set level
    log_level = (
        config.LOG_LEVEL.upper() if getattr(config, "LOG_LEVEL", None) else "INFO"
    )
    root_logger.setLevel(log_level)

    # Silence noisy libraries if needed
    logging.getLogger("uvicorn.access").propagate = False
    # If we want uvicorn access logs in JSON, we'd need to add our handler to it
    # or rely on root propagation (which implies removing uvicorn's default handlers).
    # For now, let's just ensure OUR app logs are correct.
