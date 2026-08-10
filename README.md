# JSON API Forge v0.4.1

**Config-first. Self-hosted. Multi-project. FastAPI-native.**

JSON API Forge turns strict, numbered JSON configuration into a real asynchronous backend: CRUD resources, transactional SQL/RPC operations, MongoDB resources, cache, rate limiting, media, data sources, realtime channels, authentication, OpenAPI and operational endpoints. Python hooks remain the explicit escape hatch for business logic that should not be forced into configuration.

> **v0.4.1 is a corrective hardening patch.** It fixes defects exposed by the first v0.4 GitHub-hosted CI runs without changing the project’s core architecture. The project remains **Alpha**.

## Why JSON API Forge exists

Most backends repeatedly rebuild the same infrastructure: routing, CRUD, authorization, database plumbing, caching, rate limits, validation, OpenAPI, health checks and deployment glue. Forge makes those recurring concerns declarative while keeping the important boundaries explicit. The target is not “no code”; it is **less repetitive backend code and more visible architecture**.

A project lives under `app/<Project>/` and can be split into numbered fragments:

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
└── hooks/
```

Fragments are merged alphabetically and then validated by strict Pydantic models. Unknown configuration keys are rejected.

## v0.4.1 fixes

- Removed the obsolete root `app/config` pseudo-project that was being discovered as a third application.
- Removed obsolete root `app/hooks`; hooks are project-scoped.
- Preserved the PostgreSQL fragment example under `examples/postgres-fragment.json`.
- Fixed idempotent HTTP replay responses so object replays contain `_idempotent_replay: true` and expose `X-Forge-Idempotent-Replay: true`.
- Prevented operation background hooks from running again during an idempotent replay.
- Replaced deprecated FastAPI `ORJSONResponse` runtime paths with `JSONResponse` plus `jsonable_encoder` compatibility.
- Raised the `pydantic-settings` minimum to the security-fixed line and aligned several tested dependency floors with the versions exercised on GitHub-hosted runners.
- Updated `actions/checkout` to v7 and the TypeScript reference client to TypeScript 7.0.2.
- Fixed the MongoDB example so server-controlled tenant policy fields are not client-writable.
- Updated Forge/project default version metadata and regenerated JSON Schemas.
- Added release-manifest verification to CI.

## Quick start

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install -e ".[dev]"
forge init
forge validate
forge doctor
forge dev
```

Default documentation for the example project is available at `/api/app1/v1/_docs` once the server is running.

## Core model

### Projects
Each directory under `app/` containing `app.json` or a valid manifest is an independent project. Projects have isolated prefixes, data services, roles, resources and runtime state.

### Resources
SQL resources define table/column metadata, allowed actions, filters, sorts, write fields, tenant/owner policies, cache rules and permissions. Generic CRUD is intentionally bounded by declarative policy.

### Operations / RPC
Operations execute predeclared parameterized SQL. They support transactions, row-count guards, JSON Schema inputs, cache/invalidation, and same-database transactional idempotency. User input is bound as values; it is never intended to become SQL text.

### MongoDB
Mongo resources expose bounded CRUD over configured collections. Tenant, owner and soft-delete policy fields are server-controlled.

### Data sources and API gateway
Static, JSON/YAML/CSV file and controlled outbound HTTP sources can be exposed declaratively. Outbound networking includes redirect and size controls; production deployments should still enforce network-level egress rules.

### Realtime
SSE and WebSocket event channels can use process-local memory or Redis pub/sub. Delivery is best-effort, not a durable message queue.

### Media
v0.4 implements a local-filesystem media backend with upload limits, MIME/extension allowlists, owner quotas, deduplication, signed URLs and metadata isolation. Object storage is not claimed as implemented.

### Security
- API keys are project-scoped.
- Bootstrap admin access is explicit and can be one-time.
- JWT is opt-in and can use local HS256 or external JWKS.
- SQL/custom/data/event surfaces are private unless explicitly public.
- Delegated credentials cannot silently exceed the issuer’s authority without an explicit high-trust permission.
- Trusted proxy CIDRs control whether forwarded IP/protocol headers are accepted.
- Process-level metrics/detailed readiness use a separate operator credential.

## CLI

```text
forge init                 create a safe local .env
forge new NAME             create a project
forge dev                  run a development server
forge validate             strictly validate project configuration
forge doctor               report configuration/production problems
forge doctor --production  apply production-focused diagnostics
forge routes               print generated routes
forge openapi              generate OpenAPI
forge schema               regenerate JSON Schemas
forge migrate              create required support/schema objects explicitly
forge secrets              secret tooling
```

Run `forge --help` and command-specific help for current options.

## Testing and release gates

The official CI targets:

- Python 3.11, 3.12, 3.13 and 3.14;
- branch-aware aggregate and high-risk per-module coverage gates;
- PostgreSQL 17, Redis 8 and MongoDB 8 live-service integration tests;
- TypeScript type checking on Node 22;
- package build and Docker image build;
- CodeQL;
- tracked-source `MANIFEST.sha256` verification;
- a tag-only release gate that depends on the required jobs.

A local green run is useful, but an official release should not be tagged while the canonical GitHub-hosted CI is red.

## Documentation

Start with [`docs/00-Start-Here.md`](docs/00-Start-Here.md). The documentation then moves through architecture, configuration, security, databases, operations, realtime, media, production, testing and failure modes. `docs/README.md` is the full index.

## Deployment

Native ASGI/Uvicorn is the preferred runtime, especially for SSE/WebSockets. Docker is supported through the included `Dockerfile`. A Passenger/a2wsgi bridge is included for conventional cPanel-style HTTP deployments, but it is not the preferred environment for sustained realtime workloads.

## Known limits

Forge v0.4.x is Alpha. In particular:

- same-database idempotency is not cross-system exactly-once delivery;
- realtime is not a durable broker;
- local media is not horizontally shared object storage;
- declarative SQL is trusted configuration, not an attacker-safe SQL sandbox;
- memory backends are process-local;
- schema auto-creation is not a complete production migration framework.

See `KNOWN_LIMITATIONS.md` and `docs/41-Known-Limits-and-Non-Goals.md`.

## License and official distribution

JSON API Forge is **source-available, not OSI open source**. The public source exists for transparency, auditing, study, contribution and self-hosting. The license permits private/internal modification and commercial self-hosted use, but restricts redistribution and alternative public/private distributions of the framework. Read `LICENSE` and `LICENSE-FAQ.md` before use or contribution.

The canonical project is controlled by **Cavanşir Qurbanzadə (`@Cavanshirpro`)** or a lawful successor/assignee. Official distribution remains centralized through the canonical repository or another channel explicitly designated by the Project Owner.
