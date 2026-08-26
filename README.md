# JSON API Forge Python SDK v0.5.0

This `python-library` branch is the independently packaged, pure-Python client SDK. It intentionally contains no Forge server runtime, Qt Editor, example projects, deployment files or compiled binaries.

## Install

From the branch:

```bash
python -m pip install "json-api-forge-client @ git+https://github.com/Cavanshirpro/JSON-API-Forge.git@python-library"
```

For a repeatable deployment, pin a reviewed commit SHA. The `Python SDK build` Action produces a universal `py3-none-any` wheel, source distribution, source ZIP and `SHA256SUMS`; it does not publish to PyPI automatically.

Python 3.11–3.14 is supported. The base package depends only on `httpx`.

## Application API client

```python
from json_api_forge import ForgeClient

with ForgeClient("https://api.example.com", api_key="secret-from-your-store") as forge:
    notes = forge.list_items("my-service", "notes", params={"limit": 25})
    created = forge.create_item(
        "my-service",
        "notes",
        {"name": "ship v0.5.0"},
        idempotency_key="command-0192",
    )
```

`AsyncForgeClient` provides the equivalent asyncio API. Bounded retries are opt-in; a write is never retried or failed over without an idempotency key.

## Editor control-plane client

```python
from json_api_forge import EditorControlPlaneClient

with EditorControlPlaneClient("https://forge-admin.example.com") as control:
    profile = control.login("worker.name", "password-from-a-secret-prompt")
    projects = control.projects()
    rows = control.database_rows("Billing", "primary", "invoices", limit=50)
```

The control-plane clients cover founder setup, invitation enrollment, profiles, roles, project/document access, validation, read-only database browsing, project areas, messages, notes, attachments, calls and audit records. Bearer sessions are held in a zeroable memory buffer and removed from returned authentication payloads.

Security defaults include HTTPS-only remote URLs, no ambient proxy inheritance, no redirects or retained cookies, strict same-origin paths, exact token formats, bounded response bodies, non-symlink attachment snapshots and atomic downloads. WebRTC call tickets are placed in a URL fragment for the local call client, never in an HTTP query.

## Cluster and optional integrations

`ForgeCluster` and `AsyncForgeCluster` provide deterministic routing, circuit breakers, bounded bulk work and idempotency-gated failover across multiple Forge endpoints.

YoungLion/DDM adapters remain optional:

```bash
python -m pip install "json-api-forge-client[younglion]"
# equivalent intent alias
python -m pip install "json-api-forge-client[ddm]"
```

## Develop and verify

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff format --check json_api_forge tests contract-tests scripts
ruff check json_api_forge tests contract-tests scripts
pytest -q tests
python -m build
python -m twine check dist/*
```

CI tests Linux x64/ARM64, Windows x64/ARM64 and macOS Intel/Apple Silicon, plus clean installs on Debian, Arch, Fedora, Rocky Linux 9/cPanel-family, openSUSE and Alpine/musl. A separate contract job checks out `main` and exercises this SDK against the real v0.5.0 control plane without copying server code into this branch.

See [PYTHON_LIBRARY.md](PYTHON_LIBRARY.md) for the complete API and release contract.

## License

JSON API Forge is source-available, not OSI open source. Review `LICENSE` and `LICENSE-FAQ.md`. Official distribution authority remains with Cavanşir Qurbanzadə (`@Cavanshirpro`) or a lawful successor/assignee.
