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

## Security defaults

- HTTPS is required. `allow_insecure_http=True` permits HTTP only for a loopback server.
- Embedded URL credentials, cross-host request URLs, fragments and traversal segments are rejected.
- Redirects and ambient `HTTP_PROXY`/`HTTPS_PROXY` inheritance are disabled.
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

The branch workflow validates synchronized/tag versions, tests Python 3.11–3.14 across Linux x64/ARM64, Windows 2022/2025 and macOS Intel/ARM64, runs branch-aware critical coverage gates, compares two clean wheel builds byte-for-byte, compares two sdist payloads, installs the wheel outside the checkout, verifies `py.typed`, creates SHA-256 checksums and uploads one release bundle. Checkout credentials are not persisted. It never publishes to PyPI or creates a GitHub release.
