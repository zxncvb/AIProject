import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from prometheus_client import Counter, Gauge, Histogram, generate_latest

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
except ImportError:  # pragma: no cover
    trace = None

from ..config import get_settings


logger = logging.getLogger("enterprise_ai_platform")
runs_total = Counter("ai_platform_workflow_runs_total", "Workflow runs", ["tenant", "status"])
run_failures = Counter("ai_platform_workflow_failures_total", "Workflow failures", ["tenant"])
run_duration = Histogram("ai_platform_workflow_duration_seconds", "Workflow duration", ["tenant"])
llm_calls = Counter("ai_platform_llm_calls_total", "LLM calls", ["tenant", "provider", "status"])
tool_calls = Counter("ai_platform_tool_calls_total", "Tool and plugin calls", ["tenant", "kind", "status"])
job_queue_messages = Gauge("ai_platform_job_queue_messages", "Messages waiting or pending in the reliable job stream")
job_dead_messages = Gauge("ai_platform_job_dead_messages", "Jobs in the dead-letter stream")
publication_failed = Gauge("ai_platform_publication_failed", "Failed or stopped publication deliveries")
application_deployment_failed = Gauge("ai_platform_application_deployment_failed", "Failed full-code application deployments")
approval_pending = Gauge("ai_platform_approval_pending", "Pending enterprise approval requests")


def setup_telemetry() -> None:
    settings = get_settings()
    if trace is None or not settings.otel_exporter_otlp_endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "enterprise-ai-platform"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
    trace.set_tracer_provider(provider)


def new_trace_id() -> str:
    return uuid4().hex


@asynccontextmanager
async def run_span(trace_id: str, name: str):
    started = time.perf_counter()
    tracer = trace.get_tracer("enterprise-ai-platform") if trace else None
    span_cm = tracer.start_as_current_span(name) if tracer else None
    if span_cm:
        with span_cm as span:
            span.set_attribute("ai.trace_id", trace_id)
            try:
                yield span
            finally:
                run_duration.labels("unknown").observe(time.perf_counter() - started)
    else:
        try:
            yield None
        finally:
            logger.debug("span=%s duration=%.3fs", name, time.perf_counter() - started)


def metrics_payload() -> bytes:
    return generate_latest()
