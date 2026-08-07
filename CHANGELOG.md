# Changelog

## [0.2.0] — 2026-08-07

### Added / changed
- Multiple independent applications under app/<Project>/ with mergeable JSON fragments.
- Per-project API prefixes, databases, credentials, roles, CORS policies and feature packs.
- Memory, Redis and tiered L1/L2 caches with generation-based invalidation.
- Token-bucket rate limiting, per-key traffic budgets and concurrency/backpressure protection.
- Database connection-pool tuning, readiness checks and batched asynchronous audit writes.
- Media APIs with streaming upload, MIME/size policies, hashing and deduplication.
- Messaging, social-media and gaming resource packs.
- Cursor/keyset pagination and resilient outbound HTTP client foundation.

### Migration note
- Application configuration moves from the v0.1 single-project model toward `app/<Project>/` with mergeable JSON fragments.

## [0.1.0] — 2026-08-07

- Initial configuration-driven FastAPI backend foundation with async SQL resources, API keys, RBAC, CRUD policies and cPanel entrypoint.
