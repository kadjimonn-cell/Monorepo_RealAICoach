from __future__ import annotations

import logging
import os
import socket
from urllib.parse import urlparse

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def configure_open_telemetry(app: FastAPI, service_name: str) -> bool:
    enabled = str(os.environ.get("OTEL_ENABLED") or "false").strip().lower() == "true"
    if not enabled:
        logger.info("OTEL instrumentation disabled (OTEL_ENABLED!=true)")
        return False

    endpoint = str(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint:
        logger.warning("OTEL enabled but OTEL_EXPORTER_OTLP_ENDPOINT missing; skipping OTLP exporter setup")
        return False

    endpoint_host = ""
    endpoint_port = 4317
    if "://" in endpoint:
        parsed = urlparse(endpoint)
        endpoint_host = parsed.hostname or ""
        endpoint_port = int(parsed.port or 4317)
    else:
        if ":" in endpoint:
            host_part, port_part = endpoint.rsplit(":", 1)
            endpoint_host = host_part.strip()
            try:
                endpoint_port = int(port_part)
            except Exception:
                endpoint_port = 4317
        else:
            endpoint_host = endpoint

    if not endpoint_host:
        logger.warning("OTEL endpoint could not be parsed; skipping setup")
        return False

    sock = socket.socket()
    sock.settimeout(1.0)
    try:
        sock.connect((endpoint_host, endpoint_port))
    except Exception:
        logger.warning("OTEL collector not reachable at %s:%s; skipping setup", endpoint_host, endpoint_port)
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:  # pragma: no cover
        logger.error("OTEL imports failed: %s", exc)
        return False

    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": str(os.environ.get("ENVIRONMENT") or "preview"),
        }
    )

    provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)

    excluded = ",".join(
        [
            r"/api/health",
            r"/api/system/metrics",
            r"/api/admin/system/metrics",
            r"/api/vitals/.*",
        ]
    )
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=excluded)

    try:
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except Exception:
        logger.warning("OTEL HTTPX instrumentation failed", exc_info=True)

    try:
        PymongoInstrumentor().instrument(tracer_provider=provider)
    except Exception:
        logger.warning("OTEL pymongo instrumentation failed", exc_info=True)

    try:
        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception:
        logger.warning("OTEL logging instrumentation failed", exc_info=True)

    logger.info("OTEL instrumentation active for %s -> %s", service_name, endpoint)
    return True
