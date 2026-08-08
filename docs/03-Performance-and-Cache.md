# Performance, cache and overload protection

## Database pools

Every SQL database alias has its own SQLAlchemy async engine and pool settings:

```json
{
  "pool_size": 20,
  "max_overflow": 40,
  "pool_timeout": 10,
  "pool_recycle": 1800,
  "pool_pre_ping": true
}
```

Do not multiply these values blindly. Approximate maximum possible SQL connections is influenced by:

```text
processes × projects × database aliases × (pool_size + max_overflow)
```

The DB server, cPanel account and network usually have lower real limits than the application can theoretically request.

## Cache backends

- `memory`: process-local L1 cache.
- `redis`: shared cache.
- `tiered`: memory L1 + Redis L2.

For multi-process Passenger/Uvicorn deployments, Redis is the shared source for cache generations.

## Generation-based invalidation

Cache keys include a namespace generation:

```text
app1:primary:economy_accounts:g18:<hash>
```

A mutation increments the generation. New requests no longer address old keys; the old generation expires naturally. This avoids Redis `SCAN`/wildcard deletion on hot resources.

RPCs and data sources have independent namespaces. Mutating RPCs can explicitly invalidate both resource paths and other operation names.

## Stampede protection

Forge protects a cold key in two layers:

1. per-process asyncio lock;
2. Redis distributed lock when Redis/tiered cache is used.

That reduces the “100 workers all miss and all query PostgreSQL” pattern.

## Stale-while-revalidate

`cache.stale_ttl_seconds` can keep an expired value temporarily usable while one task refreshes it:

```json
{
  "cache": {
    "default_ttl_seconds": 30,
    "stale_ttl_seconds": 15
  }
}
```

Timeline:

```text
0..30 s   fresh → return immediately
30..45 s  stale → return immediately + refresh in background
>45 s     miss → wait for loader
```

Set stale TTL to `0` for values that must never knowingly return old data, such as authoritative balances immediately after mutation.

## Fail-open cache

`cache.fail_open:true` means a cache failure should not automatically make a healthy database API unavailable. Forge can fall through to the loader when cache reads/sets fail.

Tradeoff: if a generation bump fails during a Redis outage, another process may still possess an older cache entry until its TTL expires. For strict-consistency endpoints, disable caching or configure fail-closed behavior.

## Rate limiting

Memory or Redis token buckets support steady rate + burst. API keys can override project defaults. v0.4 uses a **principal-global primary bucket**, so changing `/items/1` to `/items/2` does not mint a fresh primary quota.

An optional second budget protects the normalized FastAPI route template:

```json
{
  "rate_limit": {
    "requests": 1000,
    "window_seconds": 60,
    "burst": 200,
    "route_requests": 200,
    "route_window_seconds": 60,
    "route_burst": 40
  }
}
```

The memory limiter is bounded with `memory_max_buckets`, `memory_idle_ttl_seconds` and `memory_cleanup_interval_seconds`. These controls prevent a high-cardinality identity/path attack from growing an unbounded dictionary. Redis remains the correct choice for a quota shared by multiple workers/hosts.

## Backpressure

`max_concurrent_requests` bounds project work. With `reject_when_saturated:true`, excess requests are rejected immediately. With it disabled, waiting is still bounded by `max_queue_wait_seconds` instead of consuming unlimited memory and DB waiters.

This protects the process, but values should match actual CPU/RAM/DB capacity.

## Cursor pagination

Use cursor/keyset mode on monotonically ordered high-volume tables. Large SQL OFFSET values become progressively more expensive.

## Audit hot path

Audit events go to a bounded async queue and are batch-written. Audit DB latency therefore does not normally sit directly in every response path.

## External HTTP

The outbound HTTP service uses a long-lived connection pool, timeout, retry/backoff and a circuit breaker. This reduces socket churn and cascading failures when an upstream API is slow.


## Per-resource stale policy

The global `cache.stale_ttl_seconds` is only a default. SQL/Mongo resource cache, RPC cache and data-source config can override stale TTL. This lets a social feed use stale-while-revalidate while an economy balance explicitly uses `stale_ttl_seconds:0`.

## Rate-limiter failure policy

`rate_limit.fail_open:false` is the safer default for public abuse protection: a Redis limiter outage returns a temporary `503` instead of silently disabling limits. Set `fail_open:true` only when availability is more important than temporary enforcement and the downstream DB/API can absorb the extra traffic.


## Request-body memory protection

v0.4 applies the project body limit while ASGI request chunks are received. This covers clients that omit or lie about `Content-Length`. Endpoint-specific/media limits still apply in addition to the generic project limit.

## Failure amplification

Cache fail-open can preserve availability during Redis failure, but the miss traffic then moves to the database. Rate-limit fail-open can preserve traffic but temporarily removes an abuse budget. Capacity plans must evaluate the **degraded path**, not only the normal cached path. See `26-Operational-Failure-Modes.md`.
