# Python library

The `python-library` branch builds one pure-Python wheel and source distribution containing both the JSON API Forge runtime (`framework`) and the typed public facade (`json_api_forge`). Python 3.11–3.14 are supported.

## Git installation

```bash
python -m pip install "json-api-forge @ git+https://github.com/Cavanshirpro/JSON-API-Forge.git@python-library"
```

For reproducibility, replace the branch with a commit SHA or official tag.

## Client lifecycle

```python
from json_api_forge import AsyncForgeClient

async with AsyncForgeClient("https://forge.example.com", api_key="...") as forge:
    result = await forge.call_operation(
        "billing",
        "invoices.issue",
        {"customer_id": "cust-7"},
        idempotency_key="job-731",
    )
    print(result.data, result.request_id, result.idempotent_replay)
```

The sync and async clients support health/metadata, CRUD and operations plus the general `request` method. Nested resource paths such as `gaming/leaderboard` are supported. URL-safe item IDs and project/path segments are percent encoded; slash, backslash, traversal and control characters are rejected as ambiguous routing input.

## Secure Editor control-plane client

`EditorControlPlaneClient` and `AsyncEditorControlPlaneClient` expose the v0.5.0 account/team surface without reusing application API keys:

```python
from json_api_forge import EditorControlPlaneClient

with EditorControlPlaneClient("https://forge-admin.example.com") as control:
    signed_in = control.login("worker.name", "password-from-a-secret-prompt")
    print(signed_in.data["profile"])

    for project in control.projects().data["projects"]:
        print(project["directory"])

    rows = control.database_rows("Billing", "primary", "invoices", limit=50)
    control.post_message("project-area-id", f"Reviewed {len(rows.data['rows'])} invoices")
```

The clients cover one-time founder setup, invitation enrollment, profile changes, roles, memberships, projects/documents, validation, the read-only database browser, areas/messages, notes, bounded attachments, call tickets and audit events. Authentication responses are adopted internally and returned without `access_token`, reducing accidental token logging. The session lives in a zeroable memory buffer and is cleared on logout, close or HTTP 401.

Management requests never inherit environment proxies, follow redirects, retain cookies or use an HTTP cache. Attachment sources reject symlinks and size overflow; downloads are bounded and atomically replace only the explicit destination. WebRTC tickets can be converted to a same-origin call URL with the ticket in the URL fragment, never the HTTP query.

## Large systems

`ForgeCluster` and `AsyncForgeCluster` route across multiple Forge deployments, support deterministic rendezvous routing, bounded failover circuit breakers, per-endpoint health inspection and order-preserving bulk work. Retries are opt-in through `RetryPolicy`; POST requests are never retried or failed over unless an idempotency key is supplied. One request ID is preserved across permitted endpoint attempts so traces remain correlated.

```python
from json_api_forge import ForgeCluster, ForgeEndpoint, RetryPolicy, RoutingStrategy

endpoints = [
    ForgeEndpoint("eu-1", "https://eu-1.forge.example", api_key="..."),
    ForgeEndpoint("eu-2", "https://eu-2.forge.example", api_key="..."),
]

with ForgeCluster(endpoints, strategy=RoutingStrategy.RENDEZVOUS) as cluster:
    result = cluster.call_operation(
        "billing",
        "invoices.issue",
        {"customer_id": "cust-7"},
        routing_key="tenant-42",
        idempotency_key="invoice-job-731",
    )
```

The base clients also provide bounded pagination through `iter_items`, request-attempt observers for metrics/tracing, and retry policies with capped exponential backoff. Sync and async bulk helpers default to at most 10,000 input operations and expose an explicit `max_items` bound.

## YoungLion and DDM extras

The canonical YoungLion 0.1.x package is optional:

```bash
python -m pip install "json-api-forge[younglion]"
# or the narrower intent alias:
python -m pip install "json-api-forge[ddm]"
```

Both extras install YoungLion 0.1.x. `YoungLionForgeClient` and `DDMForgeClient` accept DDM payloads, serialize them without duplicating the integration dependency in the core wheel, and convert Forge responses back into DDM objects.

```python
from YoungLion import DDM
from json_api_forge.integrations import YoungLionForgeClient

with YoungLionForgeClient.connect("https://forge.example.com", api_key="...") as forge:
    created = forge.create_item("accounts", "profiles", DDM({"name": "Ada"}))
    print(created.data.to_dict())
```

## Security defaults

- HTTPS is required. `allow_insecure_http=True` permits HTTP only for a loopback server.
- Embedded URL credentials, cross-host request URLs, fragments and traversal segments are rejected.
- Redirects and ambient `HTTP_PROXY`/`HTTPS_PROXY` inheritance are disabled.
- Clients discard server cookies between requests; Editor bearer/setup credentials remain separate from application API keys.
- Response bodies are limited to 8 MiB by default; customize `max_response_bytes` deliberately.
- Error responses raise `ForgeHTTPError` and preserve status, detail, server request ID and `Retry-After`.
- Connection failures raise `ForgeTransportError`; oversized bodies raise `ForgeResponseTooLarge`.

## Build

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff format --check framework json_api_forge tests
ruff check framework json_api_forge tests
pytest -q
python -m build
python -m twine check dist/*
```

Following the YoungLion distribution pattern, the branch workflow validates synchronized/tag versions, tests Python 3.11–3.14 across Linux x64/ARM64, Windows 2022/2025/ARM64 and macOS Intel/ARM64, then performs clean PEP 517 installs in Debian, Arch, Fedora, Rocky Linux 9 (the cPanel family), openSUSE and Alpine/musl containers. It also runs branch-aware coverage gates, compares two clean wheel builds byte-for-byte, compares two sdist payloads, installs the wheel outside the checkout, verifies `py.typed`, creates SHA-256 checksums and uploads one release bundle. Checkout credentials are not persisted. It never publishes to PyPI or creates a GitHub release.

The Python package remains pure Python (`py3-none-any`), so a native extension would add platform risk without improving this I/O-bound client. Native frozen `forge` and `forge-server` commands are built by the main branch and downloaded by its checksum-verifying release installers.
