# JSON API Forge v0.5.0

<p align="center"><img src="assets/branding/JSON-API-FORGE_logo.png" width="240" alt="JSON API Forge logo"></p>

> This is the `exampleApps` branch. It adds 25 named, copy-ready applications under `app/`; use `main` for the intentionally example-free runtime tree. See [`EXAMPLE_APPS.md`](EXAMPLE_APPS.md).

**Config-first. Self-hosted. Multi-project. FastAPI-native.**

JSON API Forge turns strict, numbered JSON configuration into a real asynchronous backend: CRUD resources, transactional SQL/RPC operations, MongoDB resources, cache, rate limiting, media, data sources, realtime channels, authentication, OpenAPI and operational endpoints. Python hooks remain the explicit escape hatch for business logic that should not be forced into configuration.

> **v0.5.0 is the visual-authoring, secure remote-team and integration release.** It adds account-based Editor access, scoped roles, profiles, project spaces, chat, notes, WebRTC calls, a read-only database browser, policy-gated graph documents, a hardened Python SDK line, Forge-backed plugin catalog contracts and 25 copy-ready systems on `exampleApps`. The project remains **Alpha**.

## Why JSON API Forge exists

Most backends repeatedly rebuild the same infrastructure: routing, CRUD, authorization, database plumbing, caching, rate limits, validation, OpenAPI, health checks and deployment glue. Forge makes those recurring concerns declarative while keeping the important boundaries explicit. The target is not “no code”; it is **less repetitive backend code and more visible architecture**.

A project lives under `app/<Project>/` and can be split into numbered fragments:

```text
app/MyService/
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
├── graphs/
└── hooks/
```

Fragments are merged alphabetically and then validated by strict Pydantic models. Unknown configuration keys are rejected.

## v0.5.0 ecosystem

- `main` stays example-free and now validates bounded, schema-versioned, acyclic Editor graph documents behind the separate `EDITOR_ALLOW_GRAPHS` policy.
- The control plane uses one-time founder setup, hashed worker credentials, expiring sessions, ranked/scoped roles, project/document/database policy and append-only audit records; the shared-token mode is development-only compatibility.
- The `Editor` branch adds a C++20/Qt 6 node-and-wire graph, code/typed visual modes, account/team/database workspaces, Amber Gold + Graphite Gray branding, eight atomic templates, Python SDK integration and a digest-verified Plugin API v2.
- The Editor can browse plugin release records from a normal Forge resource; it validates metadata and never silently installs or executes catalog code.
- The `python-library` branch adds sync/async retry observability, bounded pagination/bulk work, multi-region routing, circuit breakers and safe failover. Optional `[younglion]` and `[ddm]` extras keep those integrations lazy.
- The `exampleApps` branch contains 25 named applications with schema, CRUD, RPC, idempotency, realtime and graph smoke coverage.
- The v0.4.2 discovery, authorization, concurrency, proxy, credential and control-plane hardening remains in force.
- Python 3.11–3.14, live PostgreSQL 17/Redis 8/MongoDB 8, package, TypeScript, container, manifest and CodeQL gates remain required.

## Quick start

```bash
git clone https://github.com/Cavanshirpro/JSON-API-Forge.git
cd JSON-API-Forge
./scripts/install.sh             # Windows: .\scripts\install.ps1
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1

forge new MyService --slug my-service
forge init
forge validate
forge doctor
forge dev
```

After release assets are attached to GitHub Releases, install a checksum-verified, platform-matched standalone build with `./scripts/install.sh --release` or `.\scripts\install.ps1 -Release`. The build workflow produces glibc/musl Linux, Windows, macOS, OCI, wheel/source and cPanel/Passenger artifacts for x64/ARM64 where the platform supports them.

The generated project documentation is available at `/api/my-service/v1/_docs` once the server is running. See [`INSTALL.md`](INSTALL.md) for editable, Git-ref and Docker installation paths.

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
Forge implements a local-filesystem media backend with upload limits, MIME/extension allowlists, owner quotas, deduplication, signed URLs and metadata isolation. Object storage is not claimed as implemented.

### Security
- API keys are project-scoped.
- Bootstrap admin access is explicit and can be one-time.
- JWT is opt-in and can use local HS256 or external JWKS.
- SQL/custom/data/event surfaces are private unless explicitly public.
- Delegated credentials cannot silently exceed the issuer’s authority without an explicit high-trust permission.
- Trusted proxy CIDRs control whether forwarded IP/protocol headers are accepted.
- Process-level metrics/detailed readiness use a separate operator credential.

### Dedicated editor control plane

The `Editor` branch contains the C++/Qt desktop editor. A server only exposes its management surface when `EDITOR_API_ENABLED=true`. `EDITOR_TOKEN` is accepted only once to create the founder account; workers then use invitation-scoped accounts and short-lived bearer sessions, never application API keys. The server independently enforces HTTPS, source IP and Host allowlists, role rank, project/document/database scopes, read-only mode, project creation, Python-hook editing and graph editing. See [`docs/42-Editor-Control-Plane.md`](docs/42-Editor-Control-Plane.md).

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

The `python-library`, `Editor` and `exampleApps` branches have branch-specific build workflows. They produce downloadable artifacts but do not publish packages or releases automatically.

A local green run is useful, but an official release should not be tagged while the canonical GitHub-hosted CI is red.

## Documentation

Start with [`docs/00-Start-Here.md`](docs/00-Start-Here.md). The documentation then moves through architecture, configuration, security, databases, operations, realtime, media, production, testing and failure modes. `docs/README.md` is the full index.

## Deployment

Native ASGI/Uvicorn is the preferred runtime, especially for SSE/WebSockets. Docker is supported through the included `Dockerfile`. A Passenger/a2wsgi bridge is included for conventional cPanel-style HTTP deployments, but it is not the preferred environment for sustained realtime workloads.

See [`docs/43-Platform-and-Hosting-Matrix.md`](docs/43-Platform-and-Hosting-Matrix.md) for Windows/Windows Server, mainstream and specialist Linux distributions, Alpine/musl, macOS, containers, cPanel/Passenger and reverse-proxy deployment paths.

## Known limits

Forge v0.5.x is Alpha. In particular:

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
