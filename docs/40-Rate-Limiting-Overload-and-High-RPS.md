# Rate Limiting, Overload, and High-RPS Design

High request volume is not solved by one rate-limit number. Forge separates authentication abuse, principal budgets, route budgets, concurrency, cache, database pools and long-lived realtime limits.

## 1. Pre-auth budget

Invalid/random API keys can force credential lookups before normal principal rate limiting. v0.4 therefore supports a coarse IP-based pre-auth token bucket before expensive authentication work.

The pre-auth budget should normally be looser than the authenticated principal budget so legitimate users behind NAT are not unintentionally capped below their configured API-key budget.

## 2. Principal-global budget

The main bucket is independent of the concrete URL path. Rotating IDs such as:

```text
GET /notes/1
GET /notes/2
GET /notes/999999
```

does not create an unlimited series of fresh principal budgets.

## 3. Route-template budget

An optional second budget can apply to the normalized route template, for example `/notes/{item_id}`. This gives endpoint-specific shaping without high-cardinality raw-path keys.

## 4. Memory backend

Memory limiting is process-local. v0.4 bounds bucket state and avoids evicting active buckets in a way that would reset quota. At capacity it uses bounded overflow behavior rather than unlimited dictionary growth.

Use this for single-process/small deployments where process-local enforcement is acceptable.

## 5. Redis backend

Redis uses atomic server-side bucket updates and Redis server time, avoiding worker clock skew. Expiry covers the actual refill duration so a large burst/slow refill combination does not reset early because the key expired first.

Use Redis when multiple workers/hosts need shared enforcement.

## 6. Fail-open vs fail-closed

A Redis rate limiter can have a configured failure policy. Public-content availability and financial/admin protection may choose differently.

Document the choice; a Redis outage should not silently change the intended security posture.

## 7. API-key lookup cache

Valid API-key metadata can be cached briefly per worker to avoid making the internal database the hottest query on every request. Default TTL is short and bounded.

Tradeoff: revocation performed on another worker may take up to the configured TTL to propagate to this worker. Set TTL to zero for immediate DB authority or keep it very small for high-RPS deployments.

## 8. Concurrency gate

Rate limits control request arrival over time. The concurrency gate controls how much work is admitted simultaneously. When saturated, configuration chooses immediate rejection or bounded waiting.

Never use an unbounded application queue as overload handling.

## 9. Database pools

Tune application DB and internal metadata DB pools independently. API-key lookup, audit and media metadata can load the internal database even when application queries are cached.

## 10. Cache stampede

Tiered/Redis cache uses single-flight/distributed coordination where configured. Per-key process locks are ephemeral/ref-counted so high-cardinality cache misses do not leave an ever-growing lock dictionary.

## 11. Realtime

WebSocket message budgets and per-worker connection ceilings are separate from ordinary request rate limiting.

## 12. Measure, do not guess

Use `scripts/load_test.py` and production telemetry to measure p50/p95/p99, RPS, pool waits and error codes. A configuration that handles thousands of cached reads may not handle the same volume of transactional writes.
