from __future__ import annotations

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
except ImportError:  # optional until requirements are installed
    CONTENT_TYPE_LATEST = "text/plain"
    Counter = Gauge = Histogram = None
    generate_latest = None

_REQUESTS = Counter("json_api_forge_requests_total", "HTTP requests", ["project", "method", "status"]) if Counter else None
_LATENCY = Histogram("json_api_forge_request_duration_seconds", "HTTP latency", ["project", "method"]) if Histogram else None
_AUDIT_DROPPED = Counter("json_api_forge_audit_dropped_total", "Audit events dropped because the bounded queue was full") if Counter else None
_AUDIT_WRITE_FAILURES = Counter("json_api_forge_audit_write_failures_total", "Failed audit database batch writes") if Counter else None
_AUDIT_QUEUE = Gauge("json_api_forge_audit_queue_size", "Current audit queue depth") if Gauge else None


def observe(project: str, method: str, status: int, seconds: float) -> None:
    if _REQUESTS is None:
        return
    _REQUESTS.labels(project=project or "global", method=method, status=str(status)).inc()
    _LATENCY.labels(project=project or "global", method=method).observe(seconds)


def observe_audit_drop(count: int = 1) -> None:
    if _AUDIT_DROPPED is not None:
        _AUDIT_DROPPED.inc(count)


def observe_audit_write_failure(count: int = 1) -> None:
    if _AUDIT_WRITE_FAILURES is not None:
        _AUDIT_WRITE_FAILURES.inc(count)


def observe_audit_queue(size: int) -> None:
    if _AUDIT_QUEUE is not None:
        _AUDIT_QUEUE.set(size)


def metrics_payload() -> tuple[bytes, str]:
    if generate_latest is None:
        return b"prometheus-client is not installed\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST
