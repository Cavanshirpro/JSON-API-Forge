# Known Limits and Non-Goals

This document intentionally describes what JSON API Forge v0.4 **does not promise**.

## 1. Not a complete BaaS clone

Forge is a config-first FastAPI runtime. It does not attempt to reproduce every product surface of large hosted backend platforms.

## 2. Feature packs are primitives

Messaging/social/gaming packs provide schemas, permissions and useful generated resources. They do not automatically implement every application-specific invariant.

Examples requiring custom policy/RPC/hook logic include:

- messaging conversation membership;
- social audience/feed ranking/block relationships;
- gaming anti-cheat/server-authoritative economy;
- marketplace fraud policy;
- guild hierarchy.

## 3. Realtime is not durable messaging

WebSocket/SSE + Redis pub/sub is best-effort fan-out. There is no built-in durable event history, consumer offsets or offline replay guarantee.

## 4. SQL idempotency is not cross-system exactly-once

Forge can atomically commit a SQL mutation and its idempotency record in the same database. It cannot make PostgreSQL + payment provider + Discord + email a single ACID transaction. The replay ledger has TTL-based retention and opportunistic indexed cleanup, but operators should still monitor database growth and choose a retry horizon appropriate to their domain.

## 5. Local media is not object storage

The implemented backend is local filesystem. Horizontal multi-host media requires shared storage architecture.

## 6. File locks are not distributed locks

JSON/YAML file mutation uses process/cross-process host locking and atomic replacement. It is not safe as a shared writable store across unrelated hosts without a distributed filesystem/lock design.

## 7. HTTP SSRF checks are not a network firewall

Application validation reduces obvious risks; production egress policy should also exist at infrastructure/network level.

## 8. SQL guardrails are not an attacker SQL sandbox

Declarative SQL is trusted server configuration. Parameter binding protects values, and DDL/read-only checks are guardrails, but Forge is not a sandbox for arbitrary attacker-supplied SQL text.

## 9. Rate limits are finite capacity controls

Memory and Redis rate limiters cannot create infinite server capacity. Database pools, CPU, file descriptors and upstream services still set hard limits.

## 10. cPanel compatibility is not native ASGI equivalence

Passenger/WSGI bridging supports useful HTTP deployments but is not the recommended path for high-volume WebSocket/realtime workloads.

## 11. Schema auto-create is not a complete migration engine

Use explicit production migrations for complex transformations/backfills/zero-downtime changes.

## 12. Audit is not immutable compliance storage

The built-in asynchronous audit writer is operational audit telemetry with bounded queues and observable failure/drop behavior. Compliance may require external immutable storage.

## 13. API-key auth cache has a revocation window

With a nonzero process-local auth-cache TTL, another worker can accept a just-revoked key until that cached entry expires. Keep TTL short or disable it when immediate revocation is required.

## 14. WebSocket application limits are not transport limits

Channel `max_message_bytes` is enforced after the ASGI server receives the message. Internet-facing deployments should also configure the ASGI server/reverse proxy with a hard WebSocket frame/message bound.

## 15. Current release maturity

v0.4 is a hardening alpha. Repository tests and CI gates raise confidence in implemented behavior; they do not certify every production workload.
