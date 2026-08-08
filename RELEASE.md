# JSON API Forge v0.4.0

**Release date:** 8 August 2026  
**Status:** Alpha hardening release  
**License:** JSON API Forge Source-Available Self-Host License 1.1 (`LicenseRef-JAF-SASH-1.1`)

v0.4.0 is a **security, reliability, architecture and developer-experience release**. It intentionally slows broad feature expansion and strengthens the config-first FastAPI runtime introduced in v0.1–v0.3.

## Why this release exists

An external review of v0.3.0 correctly identified several areas where feature breadth had outpaced production confidence: unsafe placeholder-secret onboarding, idempotency crash semantics, high-cardinality rate-limit keys, permissive defaults for newer endpoint types, limited critical-path test coverage, a monolithic application factory, incomplete request-body enforcement and insufficient release gates.

v0.4.0 addresses those issues directly rather than hiding them behind additional feature packs.

## Security and correctness highlights

- **No usable default admin/JWT secrets.** `.env.example` contains blank secret slots; `forge init` generates strong values and writes `.env` with restrictive permissions where supported.
- **Production secret validation.** `forge doctor --production` reports missing/weak secrets and unsafe production choices. Production startup can fail fast on invalid configuration.
- **One-time bootstrap administration.** Bootstrap consumption and first durable API-key creation share one internal-database transaction; concurrent first-admin attempts cannot both succeed.
- **Private by default.** SQL/RPC operations, custom endpoints, data sources and event publish/subscribe directions require permissions unless an explicit public opt-in is configured.
- **Transactional idempotency.** Idempotency records for SQL operations live in the same business database and transaction as the protected side effects. Canonical request fingerprints detect reuse of an idempotency key with a different payload.
- **Bounded rate limiting.** Principal-global budgets no longer depend on raw high-cardinality URL paths; optional normalized route-template budgets are supported. In-memory buckets expire and are capped.
- **WebSocket message throttling.** Event channels can enforce limits after connection establishment, not only during handshake.
- **Streaming request-size enforcement.** ASGI receive chunks are counted even when `Content-Length` is absent or misleading.
- **Route collision diagnostics.** `forge doctor` detects conflicting generated method/path pairs before deployment.
- **Strict declarative models.** Unknown configuration keys are rejected instead of being silently ignored.
- **Project-scoped local JWT secrets.** JWT is opt-in by default; local-HS256 apps can use independent signing secrets instead of sharing one process-wide key.
- **Safer upstream retries.** Permanent 4xx responses are not retried; POST/PATCH mutation retries require explicit opt-in and an upstream idempotency contract.
- **Realtime/cache/media edge hardening.** Redis listener readiness is synchronized, slow WebSocket clients are isolated by bounded outbound queues, cache single-flight lock state is reclaimed, and media API metadata no longer exposes physical storage keys; dedup defaults to owner scope and owner quotas use an atomic usage ledger.
- **Row-level authorization boundaries.** SQL and Mongo resources can bind rows to the authenticated principal in addition to tenant scoping; tenant/owner/soft-delete policy fields are server-controlled.
- **Credential delegation containment.** Child API keys/JWTs cannot exceed the caller's roles, permissions, tenant, expiry, rate budget or subject authority without explicit high-trust delegation/impersonation permission. Revocation follows the same containment model.
- **Reverse-proxy trust isolation.** Forwarded IP/protocol values are accepted only from configured trusted proxy CIDRs; official Uvicorn launch paths keep independent proxy rewriting disabled.
- **Operator trust boundary.** Process-wide metrics and detailed readiness use a separate operator token rather than reusing one project's admin credential.
- **Bounded API-key lookup cache.** Successful key metadata may be cached briefly per worker to reduce internal-DB pressure; same-worker create/revoke invalidates immediately and cross-worker staleness is bounded by the configured TTL.

## Architecture

- Added `framework/runtime.py` to own project-scoped SQL, MongoDB, cache, rate-limit, events, media and lifecycle services, with exception-safe partial-startup cleanup.
- Moved project route construction into `framework/routers/` and significantly reduced responsibility in `framework/factory.py`.
- Added focused CLI, doctor and schema modules so application construction is no longer the only place configuration correctness is discovered.
- Preserved the existing `app/App1/config/10-*.json` numbered-fragment model and Python hooks as the escape hatch for real business logic.

## Developer experience

New/expanded CLI surface:

```bash
forge init
forge new MyApp --preset minimal
forge dev
forge validate
forge doctor
forge doctor --production
forge routes
forge openapi
forge schema
forge migrate
forge secrets
```

v0.4.0 also includes:

- generated JSON Schemas for project manifests and fragments;
- VS Code schema associations;
- stricter typed Pydantic configuration models;
- progressive documentation beginning with `docs/00-Start-Here.md`;
- starter presets for minimal, PostgreSQL API, Discord bot and game-backend projects;
- a strict TypeScript reference client in addition to the Python client;
- `pyproject.toml` packaging and console entry points;
- Dockerfile and an example PostgreSQL/Redis/MongoDB Compose stack.

## Testing and release gates

The repository now contains substantially broader unit/component/integration coverage for configuration, CRUD helpers, SQL operations, idempotency, rate limiting, request protection, cache behavior, data sources, MongoDB helpers, media, events, audit behavior, CLI/DX and failure paths.

CI is configured to require:

- Python 3.11, 3.12, 3.13 and 3.14 test jobs;
- >=75% aggregate branch-aware coverage, >=80% for high-risk critical runtime modules, and an explicit >=75% floor for the large generated project-router assembly surface;
- package build checks;
- PostgreSQL + Redis + MongoDB live-service tests;
- TypeScript client type checking;
- Docker image build;
- a tag-only release gate dependent on all of the above.

A green workflow run is still required before this release should be described as validated on GitHub infrastructure.

## Migration notes

This release intentionally changes some permissive v0.3 behavior. Read:

- `docs/21-v0.4-Hardening-and-Migration.md`
- `docs/25-Security-Threat-Model.md`
- `docs/27-Production-Readiness-Matrix.md`

before upgrading a security-sensitive deployment. Production deployments should run `forge migrate` explicitly and can then use support-schema `validate` mode to avoid routine runtime DDL.

## Known boundaries

- JSON API Forge remains **Alpha**. This release should not be advertised as universally production-ready.
- Transactional idempotency protects side effects in the selected SQL database; it cannot make an external HTTP API, Discord action, email send or second database atomically exactly-once. Use outbox/inbox or provider idempotency for cross-system workflows.
- v0.4 implements local filesystem media only. Horizontal media deployments require an external/shared storage architecture or a future real object-storage adapter; unsupported backends are not accepted as valid configuration.
- SQL safety checks are trusted-configuration guardrails, not an SQL sandbox for attacker-controlled statements.
- cPanel/Passenger remains useful for conventional HTTP deployments; native ASGI is preferred for sustained WebSocket/SSE workloads.

## License

JSON API Forge is source-available for transparency, auditing, self-hosting and private modification. It is **not OSI open source**. Alternative public or private distributions of the framework are restricted by `LICENSE`. Official distribution remains centralized under Cavanşir Qurbanzadə (`@Cavanshirpro`) or a lawful successor/assignee.
