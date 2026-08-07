# Changelog

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
