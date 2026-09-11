import os

import structlog
from fastapi import FastAPI
from sqlalchemy.engine import Engine

logger = structlog.get_logger(__name__)

OTLP_ENDPOINT_VAR = "OTEL_EXPORTER_OTLP_ENDPOINT"


def setup_telemetry(app: FastAPI, engine: Engine) -> None:
    """Instrument the app, and export spans if a collector is configured."""
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
    except ImportError:
        logger.info(
            "tracing.unavailable",
            reason="install the 'otel' extra to enable tracing",
        )
        return

    from app.core.config import config

    resource = Resource.create({"service.name": config.app_name})
    provider = TracerProvider(resource=resource)

    endpoint = os.environ.get(OTLP_ENDPOINT_VAR)
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)

    logger.info("tracing.enabled", exporting=bool(endpoint), endpoint=endpoint)
