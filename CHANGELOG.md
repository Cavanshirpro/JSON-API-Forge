# Changelog

## [0.4.0] — 2026-08-08

### Security / reliability
- Removed usable default secrets from onboarding and added `forge init` plus production doctor checks.
- Added one-time bootstrap administration support.
- Made operations, custom endpoints, data sources and event directions private by default with explicit public opt-ins.
- Reworked SQL-operation idempotency around canonical request fingerprints and same-business-transaction persistence.
- Reworked rate limiting around bounded principal-global and normalized-route token buckets, with WebSocket message budgets.
- Added ASGI streaming request-body size enforcement and stronger overload behavior.
- Added route-collision, dependency, database-alias, secret and production-default diagnostics.
- Isolated local JWT signing per project, disabled JWT by default, and retained the global JWT secret only as a compatibility fallback with production diagnostics.
- Hardened media metadata boundaries, owner-scoped deduplication defaults and streamed-file cleanup when metadata persistence fails.
- Made outbound retry policy method-aware so non-idempotent POST/PATCH retries require explicit opt-in.
- Added Redis subscription-readiness synchronization and bounded/reclaimed cache single-flight lock state.

- Added row ownership policies for SQL/Mongo resources; protected tenant/owner/soft-delete fields are server controlled.
- Added credential delegation/impersonation containment and narrowed bootstrap to first-credential capabilities instead of general `*` authority.
- Added short bounded successful API-key metadata caching with same-worker invalidation and documented cross-worker TTL revocation semantics.
- Added trusted-proxy CIDR parsing, project-scoped host enforcement, stricter CORS validation, WebSocket host/IP/TLS/origin checks, and operator-only process telemetry.
- Added deterministic/stable pagination semantics and distinct PATCH vs PUT behavior across SQL/Mongo/file-backed resources.
- Added explicit `forge migrate` support plus schema `create`/`validate` modes; v0.4 operation idempotency support lives in the business database and legacy v0.3 metadata is not destructively dropped automatically.
- Added bounded realtime connection/queue behavior, owner-transactional media quotas, safe media batch partial-result semantics, and removed unimplemented media backends from valid configuration.
- Added bounded outbound HTTP responses, redirect-disabled egress, private-network/plain-HTTP opt-ins, and production diagnostics for risky egress.

### Architecture / DX
- Introduced project runtime management and separated project routing from the application factory.
- Added strict typed configuration (`extra=forbid`) and generated JSON Schemas with VS Code associations.
- Added `forge init`, `new`, `dev`, `doctor`, `schema`, `openapi`, `routes` and secret tooling.
- Added Python packaging metadata, Docker/Compose examples and a TypeScript reference client.
- Reorganized documentation into a progressive start-to-production path.

### Testing / CI
- Expanded critical-path unit, component, failure and concurrency tests.
- Added PostgreSQL, Redis and MongoDB live-service test definitions.
- Added Python 3.11/3.12/3.13 matrix, TypeScript typecheck, container build and tag release gate.
- Raised the aggregate branch-aware coverage floor to 75%; added independent per-module gates (>=80% for high-risk runtime modules and >=75% for the project router assembly surface).

### Migration note
- v0.4 intentionally rejects several configurations that v0.3 accepted permissively. See `docs/21-v0.4-Hardening-and-Migration.md`.

## [0.3.0] — 2026-08-07

### Added / changed
- Declarative SQL/RPC operations with bind parameters, transactions, row-count guards and idempotency.
- JSON, YAML and CSV file data sources plus controlled outbound HTTP/API gateway sources.
- Expanded declarative FastAPI endpoints, parameters, dependencies, validation, response types and OpenAPI metadata.
- WebSocket and Server-Sent Events channels with memory or Redis pub/sub backends.
- Async MongoDB resources using PyMongo AsyncMongoClient and external JWKS/Supabase Auth validation.
- Distributed cache locks, tiered cache, operation invalidation, rate limits and overload protection.
- Media quotas and signed temporary URLs, Prometheus metrics and stronger readiness checks.
- Generic async Python client SDK plus a Discord economy/PostgreSQL example.

### Migration note
- v0.3.0 keeps the v0.2 multi-application model and expands it with declarative operations, data sources, realtime, MongoDB/JWKS and broader FastAPI configuration surfaces. See `docs/20-Upgrading-from-v0.2.md`.

## [0.2.0] — 2026-08-07

- Added multi-project JSON fragments, Redis/tiered caches, token-bucket rate limiting, overload protection, media, messaging/social/gaming packs and production scaling controls.

## [0.1.0] — 2026-08-07

- Initial configuration-driven FastAPI backend foundation.
