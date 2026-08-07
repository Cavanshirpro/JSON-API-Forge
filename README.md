# JSON API Forge v0.3.0

**Creator / current project owner:** Cavanşir Qurbanzadə ([@Cavanshirpro](https://github.com/Cavanshirpro))  
**Canonical repository:** https://github.com/Cavanshirpro/JSON-API-Forge  
**License:** JSON API Forge Source-Available Self-Host License 1.1 — source-available, not OSI open source.


![Version](https://img.shields.io/badge/version-0.3.0-blue) ![License](https://img.shields.io/badge/license-source--available-orange) ![FastAPI](https://img.shields.io/badge/runtime-FastAPI-009688)

> **Current release.** Declarative backend runtime with SQL/RPC operations, data sources, realtime, MongoDB, Supabase Auth and expanded FastAPI surfaces.

JSON API Forge is a configuration-driven backend runtime built around FastAPI. Its long-term goal is to move reusable backend infrastructure—database routing, API policies, authentication, authorization, caching, limits, resource definitions and integration behavior—into application configuration under `app/`, while reserving Python hooks for logic that genuinely needs code.

## License at a glance

JSON API Forge is **source-available, not OSI open source**. You may inspect the source, self-host official releases, use them commercially, and privately modify them for your own deployment. You may **not redistribute** the framework or publish an alternative modified/unmodified distribution, package, image or maintained fork, except for the narrow contribution-fork workflow described in `LICENSE`.

See [`LICENSE`](LICENSE), [`LICENSE-FAQ.md`](LICENSE-FAQ.md), [`NOTICE.md`](NOTICE.md), [`OWNERSHIP.md`](OWNERSHIP.md), [`AUTHORS.md`](AUTHORS.md), and [`GOVERNANCE.md`](GOVERNANCE.md).

## Release information

- Version: **0.3.0**
- Release notes: [`RELEASE.md`](RELEASE.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Publishing all three historical releases: [`GITHUB_PUBLISHING.md`](GITHUB_PUBLISHING.md)
- Release asset guidance: [`RELEASE_ASSETS.md`](RELEASE_ASSETS.md)
- Ownership and future company transfer: [`OWNERSHIP.md`](OWNERSHIP.md)

---

JSON API Forge is a **multi-application, JSON-defined backend runtime built on FastAPI**. The framework lives in `framework/`; almost all application-specific configuration lives under `app/<AppName>/`.

The target workflow is:

```text
Write framework once
        ↓
app/App1/*.json  → App1 API
app/App2/*.json  → App2 API
app/Game/*.json  → Game API
app/DiscordBot/*.json → Bot API
```

A project can be split across any number of JSON fragments:

```text
app/App1/
├── app.json
├── config/
│   ├── 10-databases.json
│   ├── 20-security.json
│   ├── 30-performance.json
│   ├── 40-resources.json
│   ├── 50-features.json
│   ├── 60-custom-endpoints.json
│   ├── 70-economy-rpc.json
│   └── 80-data-events.json
├── data/
│   └── catalog.json
└── hooks/
```

`app.json` is loaded first, then `config/*.json` is merged in lexical order. Dictionaries merge recursively, arrays append, and later scalar values override earlier values.

## 0.3 highlights

- Declarative SQL/RPC operations with named bind parameters, transaction support and JSON Schema request validation.
- SQL operations may read from `$body.*`, `$query.*`, `$path.*`, `$header.*`, `$principal.*` and `$request.id` without string-building SQL.
- Dangerous/multi-statement SQL is rejected by the declarative operation engine unless explicitly permitted.
- Row-count guards make money transfer/update workflows roll back when an expected row was not changed.
- Cross-worker idempotency reservations for retry-safe write operations; duplicate requests claim the key before side effects.
- JSON, YAML and CSV files can become API data sources.
- Writable JSON/YAML sources use per-source locks and atomic file replacement.
- HTTP data sources let your server operate as a controlled API gateway/proxy to another service.
- Declarative custom endpoint response types: JSON, text, HTML, redirect, stream, file and empty response.
- JSON Schema request validation for RPC and custom endpoints.
- Declarative FastAPI dependencies using trusted Python callable references.
- Per-project Swagger UI, ReDoc and filtered OpenAPI endpoints.
- OpenAPI webhook documentation declarations.
- Server-Sent Events (SSE) and WebSocket event channels.
- Memory realtime for one worker or Redis pub/sub for multi-worker/multi-server realtime.
- Prometheus metrics endpoint.
- Advanced resource filters (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `like`, `ilike`, `isnull`), text search, count and optional batch create.
- Memory, Redis and tiered L1/L2 caches with generation invalidation.
- Distributed Redis cache locks to reduce cross-worker cache stampedes.
- Operation cache invalidation so writes can invalidate cached read RPCs as well as resource caches.
- Redis/in-memory token-bucket rate limits, per-key quotas, concurrency backpressure and DB pools.
- API keys, role inheritance, wildcard permissions, tenant binding, local JWT or external JWKS JWT validation, and audit logging.
- Media upload/download, MIME/extension limits, owner quotas, hashing/deduplication and signed temporary read URLs.
- Messaging, social and gaming resource packs.
- Async MongoDB document resources through current PyMongo AsyncMongoClient support.
- Supabase Auth integration through configurable JWKS/issuer/audience claim mapping.
- Generic async Python client SDK for bots, plugins, apps and game servers.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python scripts/generate_secret.py
python scripts/validate_config.py
python run.py
```

Then inspect:

```text
/docs
/health
/ready
/metrics
/api/app1/v1/_docs
/api/app1/v1/_redoc
/api/app1/v1/_openapi.json
```

## Discord economy example

The included App1 has an economy example. A bot does **not** connect to PostgreSQL and does **not** accept arbitrary SQL from Discord users. It calls a narrow RPC:

```http
POST /api/app1/v1/rpc/economy.transfer
X-API-Key: <bot key>
Idempotency-Key: <unique interaction/retry key>
Content-Type: application/json

{"from_user":"111","to_user":"222","amount":50}
```

The server executes the JSON-defined debit, credit and ledger statements inside one transaction. If debit/credit does not update exactly one row, the transaction is rolled back.

See `docs/08-Discord-Economy-and-PostgreSQL.md` and `examples/discord_economy/`.

## JSON data as an API

This configuration:

```json
{
  "data_sources": [
    {
      "name": "catalog-file",
      "path": "content/catalog",
      "type": "json_file",
      "file": "data/catalog.json",
      "read_permission": "content.catalog.read",
      "write_permission": "content.catalog.write",
      "writable": true
    }
  ]
}
```

turns a project-local JSON file into an API. Requests still go to your FastAPI server; the server reads/updates the file and returns the response.

## Production guidance

For one worker, memory cache/rate limits/realtime are acceptable. For multiple workers or servers, use Redis for shared cache, rate limits and realtime. PostgreSQL/MySQL should use tuned async connection pools. Do not set pool/concurrency limits higher than the real cPanel/VPS resource limits.

cPanel Passenger can host normal HTTP API traffic through the included WSGI bridge. Native ASGI (Uvicorn/Hypercorn behind a reverse proxy) is the recommended deployment when WebSockets, long-lived SSE, high concurrency or multiple workers matter.

## Documentation index

- `docs/01-Architecture.md`
- `docs/02-Multi-Project-Configuration.md`
- `docs/03-Performance-and-Cache.md`
- `docs/04-Security-and-Protection.md`
- `docs/05-Media.md`
- `docs/06-Messaging-Social-Gaming.md`
- `docs/07-Production-Scaling.md`
- `docs/08-Discord-Economy-and-PostgreSQL.md`
- `docs/09-RPC-and-SQL-Operations.md`
- `docs/10-Data-Sources-and-API-Gateway.md`
- `docs/11-FastAPI-Declarative-Features.md`
- `docs/12-Client-SDK-and-Plugins.md`
- `docs/13-JSON-Language-Reference.md`
- `docs/14-Operations-and-Production-Checklist.md`
- `docs/15-MongoDB.md`
- `docs/16-Supabase-Auth-and-PostgreSQL.md`
- `docs/17-Transactions-Idempotency-and-Consistency.md`
- `docs/18-Recipes-and-Decision-Guide.md`
- `docs/19-Generated-Endpoint-Map.md`
- `docs/20-Upgrading-from-v0.2.md`
- `docs/cPanelGuide.md`

## Security boundary

JSON should declare infrastructure, policies and reusable operations. Never expose a generic endpoint that executes arbitrary SQL supplied by an untrusted client. The operation engine intentionally uses predeclared SQL plus bind parameters. Business-critical rules such as anti-cheat, payment settlement, Discord command authorization and ownership checks should be represented as restrictive operations or trusted Python hooks and covered by tests.

## Dependency files

`requirements.txt` contains the runtime dependencies for FastAPI/ASGI, configuration validation, async SQL drivers, JWT/JWKS crypto, MongoDB, Redis, HTTP gateway, metrics and the cPanel WSGI bridge. `requirements-dev.txt` adds tests/lint/type-checking. The standalone Discord example has its own `examples/discord_economy/requirements.txt` so `discord.py` is not forced onto deployments that do not use Discord.

## Validation commands

```bash
python forge.py validate
python forge.py routes
python -m compileall -q framework app clients examples
pytest -q
```

## Repository policy

Only Cavanşir Qurbanzadə (@Cavanshirpro), or a lawful successor/assignee, may designate Official Releases or authorize alternative distribution. External contributions are welcome through the canonical repository subject to the CLA and project governance. Do not commit `.env`, credentials, database files, private keys, production logs or sensitive user data.