# JSON API Forge v0.3.0

**Release date:** 7 August 2026  
**Status:** Current release  
**License:** JSON API Forge Source-Available Self-Host License 1.1 (`LicenseRef-JAF-SASH-1.1`)

Declarative backend runtime with SQL/RPC operations, data sources, realtime, MongoDB, Supabase Auth and expanded FastAPI surfaces.

## Highlights

- Declarative SQL/RPC operations with bind parameters, transactions, row-count guards and idempotency.
- JSON, YAML and CSV file data sources plus controlled outbound HTTP/API gateway sources.
- Expanded declarative FastAPI endpoints, parameters, dependencies, validation, response types and OpenAPI metadata.
- WebSocket and Server-Sent Events channels with memory or Redis pub/sub backends.
- Async MongoDB resources using PyMongo AsyncMongoClient and external JWKS/Supabase Auth validation.
- Distributed cache locks, tiered cache, operation invalidation, rate limits and overload protection.
- Media quotas and signed temporary URLs, Prometheus metrics and stronger readiness checks.
- Generic async Python client SDK plus a Discord economy/PostgreSQL example.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Generate strong secrets before starting the server. Never use the placeholder values from `.env.example` in production.

## Validate this release

```bash
python forge.py validate
python forge.py routes
python -m compileall -q framework app clients examples
pytest -q
```

## Known boundaries

- S3-compatible object-storage adapters are intentionally not claimed as implemented in this release.
- Heavy distributed jobs should use an external queue/worker architecture rather than FastAPI BackgroundTasks.
- Native ASGI deployment is recommended for high-concurrency WebSocket/SSE workloads.
- Security-critical business invariants still require carefully designed operations/hooks and tests.

## License model

The source is public for transparency, review and auditing, and official releases may be self-hosted and privately modified. This is **not an OSI-approved open-source license**: redistribution of JSON API Forge or modified/alternative versions is not permitted except for the narrow contribution-fork exception described in `LICENSE`.

Read `LICENSE`, `LICENSE-FAQ.md`, `NOTICE.md` and `GOVERNANCE.md` before redistribution-related use.

## GitHub Release asset

Attach the Project-Owner-published `JSON-API-Forge-v0.3.0-GitHub.zip` archive to the GitHub Release if you want a canonical downloadable artifact in addition to GitHub's automatically generated source archives.
