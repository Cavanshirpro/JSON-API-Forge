from __future__ import annotations

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
except ImportError:  # optional until requirements are installed
    CONTENT_TYPE_LATEST = "text/plain"
    Counter = Histogram = None
    generate_latest = None

_REQUESTS = Counter("json_api_forge_requests_total", "HTTP requests", ["project", "method", "status"]) if Counter else None
_LATENCY = Histogram("json_api_forge_request_duration_seconds", "HTTP latency", ["project", "method"]) if Histogram else None


def observe(project: str, method: str, status: int, seconds: float) -> None:
    if _REQUESTS is None:
        return
    _REQUESTS.labels(project=project or "global", method=method, status=str(status)).inc()
    _LATENCY.labels(project=project or "global", method=method).observe(seconds)


def metrics_payload() -> tuple[bytes, str]:
    if generate_latest is None:
        return b"prometheus-client is not installed\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST
