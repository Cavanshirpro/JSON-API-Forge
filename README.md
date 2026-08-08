# JSON API Forge v0.4.0

**Creator / current project owner:** Cavanşir Qurbanzadə ([@Cavanshirpro](https://github.com/Cavanshirpro))  
**Canonical repository:** https://github.com/Cavanshirpro/JSON-API-Forge  
**License:** JSON API Forge Source-Available Self-Host License 1.1 — source-available, not OSI open source.

![Version](https://img.shields.io/badge/version-0.4.0-blue) ![Status](https://img.shields.io/badge/status-alpha-yellow) ![Runtime](https://img.shields.io/badge/runtime-FastAPI-009688) ![License](https://img.shields.io/badge/license-source--available-orange)

> **v0.4.0 is a hardening and developer-experience release.** The project remains Alpha. This release deliberately prioritizes security defaults, idempotency correctness, bounded resource usage, configuration validation, testability, CI, CLI tooling, packaging, and documentation over adding another large feature pack.

JSON API Forge is a **config-first, self-hosted, multi-project backend runtime built on FastAPI**. It turns project-local JSON configuration into API resources, SQL/RPC operations, data sources, authentication/authorization policies, cache/rate-limit behavior, realtime channels, media endpoints, OpenAPI documentation, and other reusable backend infrastructure.

The design goal is not “write arbitrary business logic in JSON.” The design goal is:

```text
reusable backend infrastructure  -> JSON configuration
application-specific logic       -> trusted Python hooks
clients/plugins/bots              -> HTTP / SSE / WebSocket API
```

That boundary is intentional. JSON provides a discoverable, reviewable declarative contract; Python remains the escape hatch for logic that genuinely requires code.

---

## What problem does Forge solve?

Many applications repeatedly rebuild the same backend layers:

- database connections and pooling;
- CRUD routing;
- role and permission checks;
- API keys and JWT verification;
- tenant boundaries;
- caching and invalidation;
- rate limiting and overload protection;
- request validation;
- media endpoints;
- external API gateways;
- transactional server-side operations;
- OpenAPI/Swagger documentation;
- deployment health/readiness endpoints.

Forge moves those repeatable concerns into a shared runtime. An application normally lives under one directory:

```text
app/
├── DiscordBot/
│   ├── app.json
│   ├── config/
│   │   ├── 10-databases.json
│   │   ├── 20-security.json
│   │   ├── 30-performance.json
│   │   ├── 40-resources.json
│   │   └── 50-economy-rpc.json
│   ├── data/
│   └── hooks/
├── Game/
│   └── ...
└── Admin/
    └── ...
```

`app.json` is loaded first. `config/*.json` files are then loaded in lexical order. Dictionaries merge recursively; declaration collections such as `resources` and `operations` append, while policy/configuration arrays such as CORS origins, trusted hosts and allowlists are replaced by the later fragment. Later scalar values override earlier values. See [`docs/36-Configuration-Merge-Semantics.md`](docs/36-Configuration-Merge-Semantics.md).

---

## v0.4.0 priorities

### 1. Secure-by-default declarative endpoints

RPC operations, custom endpoints, data sources, and event channels are now **private by default**. Public access must be explicit.

```json
{
  "operations": [
    {
      "name": "status.public",
      "path": "rpc/status.public",
      "method": "GET",
      "public": true,
      "database": "primary",
      "statements": []
    }
  ]
}
```

For file/data-source APIs, `public` applies to reads only. Public mutation requires the stronger, separate opt-in `public_write: true`.

### 2. Strong startup validation

All declarative configuration models reject unknown fields. A typo such as `rate_limti` is no longer silently ignored.

Forge also performs semantic diagnostics for:

- route collisions;
- missing database aliases;
- missing MongoDB aliases;
- missing named dependencies;
- dangerous production defaults;
- missing/weak bootstrap or JWT secrets;
- Redis-backed features without `REDIS_URL`;
- risky production choices such as wildcard CORS/trusted hosts or process-local rate limiting.

Use:

```bash
forge validate
forge doctor
forge doctor --production
```

`forge doctor --production` is intentionally stricter and may refuse a public checkout until deployment secrets have been generated.

### 3. Safe initialization

The public `.env.example` contains no usable admin/JWT credentials. Generate a local gitignored `.env` with:

```bash
forge init
```

or for a production-intended environment file:

```bash
forge init --production
```

The bootstrap administrator is one-time by default. Use it to create a persistent, narrowly scoped API key and then stop relying on the bootstrap credential.

### 4. Transactional idempotency for database operations

Idempotent SQL/RPC operations now store their idempotency record **inside the same business database transaction** as the operation side effects. The idempotency identity includes a canonical request fingerprint, so reusing a key with a different payload returns a conflict instead of replaying an unrelated response.

This closes the v0.3 crash window where a business transaction could commit before a separate idempotency completion record was persisted. The v0.4 replay ledger also has TTL-based retention plus throttled indexed cleanup so one-time keys do not accumulate forever.

Important scope: this atomic guarantee applies when all protected side effects occur in the **same SQL database transaction**. It is not a magical exactly-once guarantee across PostgreSQL + an external payment provider + Discord + email. For those workflows, use an outbox/inbox or durable job architecture.

### 5. Rate-limit and overload hardening

The primary request budget is now principal-global instead of using the raw concrete URL path. Rotating `/items/1`, `/items/2`, `/items/3` no longer creates unlimited fresh primary buckets.

An optional second budget may protect a normalized FastAPI route template. In-memory buckets are bounded and expire when idle. WebSocket channels may also define per-message request/window/burst limits.

For multiple workers or multiple servers, use Redis-backed rate limiting.

### 6. Streaming request-body limits

Request size protection is implemented as ASGI middleware that counts received chunks. It therefore does not rely only on a client-supplied `Content-Length` header.

### 7. Runtime modularization

The application factory no longer owns every project service and route behavior directly. Project service lifecycle is separated into `framework/runtime.py`, while project route registration lives under `framework/routers/`.

This is an architectural cleanup, not a claim that refactoring is finished. Route builders can be split further as the project grows.

### 8. Developer CLI

v0.4 introduces an installable `forge` command:

```text
forge new
forge init
forge validate
forge doctor
forge routes
forge schema
forge openapi
forge migrate
forge dev
forge secrets
```

### 9. IDE schema support

Pydantic configuration models generate JSON Schemas into `schemas/`. The repository includes VS Code schema associations. PyCharm can map the same schemas manually.

### 10. Reliability gates

The repository CI is structured around Python 3.11, 3.12, 3.13, and 3.14 plus PostgreSQL, Redis, and MongoDB service-container integration tests. Release tags depend on the unit and integration gates.

### 11. Project-isolated JWT and safer external I/O

JWT is disabled by default. Projects that use local HS256 can reference their own signing secret (for example `"jwt_secret":"$env:APP1_JWT_SECRET"`) instead of implicitly sharing one process-wide identity key. HTTP data sources retry only transient failures and do not automatically replay POST/PATCH mutations unless `retry_non_idempotent:true` is an explicit, reviewed choice.

### 12. Realtime/cache/media reliability edges

Redis event listeners wait for subscription readiness before accepting first-event delivery, local cache single-flight lock state is ephemeral, and media responses no longer expose internal storage keys. Media deduplication is owner-scoped by default to avoid cross-user metadata disclosure.

---

## Five-minute start

### 1. Create a virtual environment

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Install

For a repository checkout:

```bash
pip install -e .
```

For development/testing:

```bash
pip install -e ".[dev]"
```

`requirements.txt` and `requirements-dev.txt` are also provided for environments that prefer requirements files.

### 3. Generate local secrets

```bash
forge init
```

Do **not** commit `.env`.

### 4. Validate configuration

```bash
forge validate
forge doctor
```

### 5. Run

```bash
forge dev
```

or:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then inspect:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/ready
http://127.0.0.1:8000/api/app1/v1/_docs
http://127.0.0.1:8000/api/app1/v1/_openapi.json
```

Start with [`docs/00-Start-Here.md`](docs/00-Start-Here.md), not the entire documentation set.

---

## Create a new app

```bash
forge new MyBot --slug my-bot --preset discord-bot
```

Available starter presets in v0.4:

- `minimal`
- `postgres-api`
- `discord-bot`
- `game-backend`

A generated project remains ordinary JSON and Python files. There is no hidden cloud control plane required to understand the deployment.

---

## Example: SQL resource

```json
{
  "resources": [
    {
      "database": "primary",
      "table": "notes",
      "path": "notes",
      "auto_create": true,
      "columns": {
        "id": {"type": "integer", "primary_key": true, "nullable": false},
        "title": {"type": "string", "nullable": false, "max_length": 200},
        "content": {"type": "text"}
      },
      "writable_fields": ["title", "content"],
      "allowed_filters": ["title"],
      "allowed_sort": ["id", "title"],
      "permissions": {
        "list": "notes.list",
        "read": "notes.read",
        "create": "notes.create",
        "update": "notes.update",
        "delete": "notes.delete"
      }
    }
  ]
}
```

Forge generates list/read/create/update/delete routes for the configured project prefix. Clients never need direct PostgreSQL credentials.

---

## Example: Discord economy operation

A Discord bot should call a narrow server operation rather than sending arbitrary SQL:

```http
POST /api/app1/v1/rpc/economy.transfer
X-API-Key: <bot-specific-key>
Idempotency-Key: discord:<interaction-id>
Content-Type: application/json

{"from_user":"111","to_user":"222","amount":50}
```

The SQL statements are trusted server configuration, use bind parameters, run in a database transaction, and may enforce expected row counts. The client supplies values, not SQL syntax.

See:

- [`docs/08-Discord-Economy-and-PostgreSQL.md`](docs/08-Discord-Economy-and-PostgreSQL.md)
- [`docs/09-RPC-and-SQL-Operations.md`](docs/09-RPC-and-SQL-Operations.md)
- [`docs/17-Transactions-Idempotency-and-Consistency.md`](docs/17-Transactions-Idempotency-and-Consistency.md)

---

## Example: JSON file behind an API

```json
{
  "data_sources": [
    {
      "name": "catalog",
      "type": "json_file",
      "path": "content/catalog",
      "file": "data/catalog.json",
      "permission": "content.catalog.read",
      "write_permission": "content.catalog.write",
      "writable": true
    }
  ]
}
```

The request still reaches your Forge server. The server applies auth/policy, reads or mutates the project-local file, and sends the response. JSON/YAML mutation uses locking plus atomic replacement on the local host.

For a deliberately public read-only source:

```json
{
  "name": "public-catalog",
  "type": "json_file",
  "file": "data/public.json",
  "public": true
}
```

Public mutation requires both `writable: true` and `public_write: true`; it is never implied by `public: true`.

---

## Supported runtime surfaces

v0.4 retains the broad v0.3 feature set while focusing engineering work on the core:

- SQL resources through SQLAlchemy Async;
- PostgreSQL, MySQL/MariaDB, SQLite;
- MongoDB resources through PyMongo Async;
- local JWT and external JWKS verification;
- API keys, roles, inheritance, wildcard permissions and tenant binding;
- declarative SQL/RPC operations;
- JSON Schema request validation;
- custom FastAPI/Python hook endpoints;
- JSON/YAML/CSV/static/HTTP data sources;
- memory/Redis/tiered cache;
- memory/Redis token-bucket rate limits;
- SSE and WebSocket channels;
- local filesystem media storage, bounded owner quotas, batch partial-result semantics, and signed temporary reads;
- Prometheus metrics;
- project-scoped OpenAPI/Swagger/ReDoc;
- messaging/social/gaming secure schema/resource primitives (domain-specific membership, visibility, anti-cheat and authoritative game mutations still belong in policy/RPC/hooks);
- Python reference client;
- TypeScript `fetch()` reference client;
- cPanel Passenger compatibility for normal HTTP traffic;
- native ASGI deployment path for WebSocket/high-concurrency workloads.

Not every surface has the same production maturity. See [`docs/27-Production-Readiness-Matrix.md`](docs/27-Production-Readiness-Matrix.md).

---

## Cache architecture

Forge supports:

```text
memory:  request -> local memory -> database
redis:   request -> Redis -> database
tiered:  request -> local L1 -> Redis L2 -> database
```

Resource cache invalidation uses a generation number rather than scanning and deleting every derived key. A write increments the namespace generation; future reads address the new generation while old keys expire naturally.

Stale-while-revalidate is appropriate only where stale data is acceptable. Do not blindly enable stale responses for balances, authorization decisions, inventory settlement, or other correctness-sensitive state.

---

## Security model

Forge is designed around these boundaries:

1. **Configuration is trusted server-side input.** Repository configuration must be code-reviewed.
2. **HTTP/WebSocket clients are untrusted.** Values are validated and permissions enforced server-side.
3. **SQL text in declarative operations is trusted configuration.** Regex checks are guardrails against mistakes; they are not a SQL sandbox for attacker-controlled SQL.
4. **Static API keys are service credentials.** Give each bot/plugin/server a narrow key and quota. Do not ship a privileged API key inside an untrusted desktop/mobile/browser client.
5. **Hooks are application code.** A hook can bypass assumptions if written incorrectly; test and review it like ordinary backend code.
6. **One database transaction cannot make external systems exactly-once.** Use durable event/outbox designs for cross-system workflows.
7. **API-key auth caching has a bounded revocation window across workers.** The database remains authoritative; same-worker create/revoke invalidates immediately, while another worker can retain a previously successful lookup until the short configured TTL expires. Set `api_key_cache_ttl_seconds: 0` when immediate per-request DB authority is required.
8. **Operator telemetry uses a separate credential.** Process-wide `/metrics` and detailed readiness are not automatically exposed to per-project admin API keys.

Read [`docs/25-Security-Threat-Model.md`](docs/25-Security-Threat-Model.md) and [`docs/35-Credential-Delegation-JWT-and-Operator-Trust.md`](docs/35-Credential-Delegation-JWT-and-Operator-Trust.md).

---

## Production deployment

Before any production deployment:

```bash
forge validate
forge doctor --production
pytest
```

For multiple workers or horizontal scaling, prefer:

```text
Reverse proxy / load balancer
           |
           v
      ASGI workers
           |
     JSON API Forge
       /    |     \
PostgreSQL Redis  optional external/shared media storage
```

Use Redis for shared rate limiting/cache/realtime when state must be consistent across processes. v0.4 implements local filesystem media only; it is host-local and must not be treated as horizontally shared object storage. A real object-storage adapter should be introduced only with an implementation and tests.

A `Dockerfile` and `docker-compose.example.yml` are included as reproducible deployment examples. They do not remove the need for real secrets, backups, TLS, migrations, monitoring, or capacity planning.

For cPanel, see [`docs/cPanelGuide.md`](docs/cPanelGuide.md). Passenger/WSGI compatibility is intended for ordinary HTTP traffic; native ASGI is the preferred path for WebSockets, long-lived SSE, and high concurrency.

---

## Documentation

Start here:

- [`docs/README.md`](docs/README.md) — documentation map
- [`docs/00-Start-Here.md`](docs/00-Start-Here.md) — first application
- [`docs/21-v0.4-Hardening-and-Migration.md`](docs/21-v0.4-Hardening-and-Migration.md) — v0.3 → v0.4 behavior changes
- [`docs/22-CLI-and-Developer-Experience.md`](docs/22-CLI-and-Developer-Experience.md) — CLI workflow
- [`docs/23-Testing-CI-and-Reliability.md`](docs/23-Testing-CI-and-Reliability.md) — test and release gates
- [`docs/24-JSON-Schema-and-IDE-Setup.md`](docs/24-JSON-Schema-and-IDE-Setup.md) — VS Code/PyCharm setup
- [`docs/25-Security-Threat-Model.md`](docs/25-Security-Threat-Model.md) — security assumptions
- [`docs/26-Operational-Failure-Modes.md`](docs/26-Operational-Failure-Modes.md) — failure handling
- [`docs/27-Production-Readiness-Matrix.md`](docs/27-Production-Readiness-Matrix.md) — maturity by subsystem
- [`docs/28-v0.4-Verification-Report.md`](docs/28-v0.4-Verification-Report.md) — verified evidence and release-CI boundary
- [`docs/29-Row-Ownership-and-Authorization.md`](docs/29-Row-Ownership-and-Authorization.md) — tenant/owner row policy
- [`docs/30-Database-Schema-Lifecycle-and-Migrations.md`](docs/30-Database-Schema-Lifecycle-and-Migrations.md) — `forge migrate` and validate-mode production startup
- [`docs/31-Reverse-Proxy-Trust-TLS-and-Client-IP.md`](docs/31-Reverse-Proxy-Trust-TLS-and-Client-IP.md) — proxy trust boundary
- [`docs/33-Realtime-Delivery-and-Backpressure.md`](docs/33-Realtime-Delivery-and-Backpressure.md) — bounded realtime semantics
- [`docs/35-Credential-Delegation-JWT-and-Operator-Trust.md`](docs/35-Credential-Delegation-JWT-and-Operator-Trust.md) — delegation and operator trust
- [`docs/40-Rate-Limiting-Overload-and-High-RPS.md`](docs/40-Rate-Limiting-Overload-and-High-RPS.md) — high-RPS controls
- [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — explicit project limits/non-goals

The older deep-dive documents remain available for SQL/RPC, media, MongoDB, Supabase Auth, cPanel, cache, and feature packs.

---

## Testing locally

Fast unit/component suite:

```bash
pytest -q
```

Coverage and critical-module gate:

```bash
pytest \
  --cov=framework \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  -q

python scripts/check_critical_coverage.py coverage.json
```

`pyproject.toml` enforces a **75% aggregate branch-aware coverage floor**. The second command is deliberately stricter for security/reliability-critical runtime modules; a high aggregate percentage cannot hide an untested authorization, transaction, cache, media, or rate-limit path.

The repository also contains integration tests for PostgreSQL, Redis, and MongoDB. They require those services and their Python drivers. GitHub CI provisions real service containers for these tests.

A test that is skipped because a service/driver is unavailable is **not** evidence that the integration passed. Release claims should distinguish local pure tests from live-service CI results.

---

## Packaging

The project has PEP 621 metadata in `pyproject.toml` and exposes:

```text
forge
json-api-forge
```

entry points when installed.

Build verification:

```bash
python -m build
```

or, in an offline environment with build dependencies already installed:

```bash
python -m pip wheel --no-deps --no-build-isolation .
```

---

## License

JSON API Forge is **source-available, not OSI open source**. The source is public for transparency, review, security inspection, support, and contributions to the canonical project. The license permits self-hosting and private deployment modifications but does not permit publishing an alternative distribution of the framework.

Read:

- [`LICENSE`](LICENSE)
- [`LICENSE-FAQ.md`](LICENSE-FAQ.md)
- [`NOTICE.md`](NOTICE.md)
- [`OWNERSHIP.md`](OWNERSHIP.md)
- [`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md)

Only Cavanşir Qurbanzadə (@Cavanshirpro), or a lawful successor/assignee, may designate Official Releases or authorize alternative distribution under the project license.

---

## Status

JSON API Forge v0.4.0 should be evaluated as an **Alpha hardening release**, not as a blanket claim of production readiness for financial settlement, payments, critical identity, or data-loss-sensitive workloads. The project is intentionally adding evidence—tests, CI gates, diagnostics, threat modeling, and documented failure boundaries—before making stronger reliability claims.
