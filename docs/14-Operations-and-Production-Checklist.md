# Operations and production checklist

## Secrets and identity

- Replace every `CHANGE_ME` value before deployment.
- Keep `.env` and database credentials outside public/static web roots.
- Use the bootstrap key only to provision ordinary admin/service keys; rotate it when appropriate.
- Give each bot/plugin/service a separate API key with minimum permissions and its own traffic budget.
- Browser/mobile public clients should normally use user JWTs rather than a reusable privileged API key.
- In external JWKS mode, configure issuer, audience and an explicit algorithm allow-list.

## Database

- Use PostgreSQL/MySQL for concurrent relational production writes; SQLite is primarily development/single-process convenience.
- Size `pool_size + max_overflow` against the actual DB connection quota across **all** workers.
- Keep `pool_pre_ping:true` for long-running hosted environments where stale connections occur.
- Use explicit Alembic/manual migrations for mature schemas; `auto_create` is not a migration strategy.
- Enforce important truth with DB constraints as well as JSON validation.
- Back up and test restoration.

## Money, inventory, purchases

- Use named RPC operations, not arbitrary caller SQL.
- Keep related mutations in one transaction.
- Use `require_rowcount_*` guards for invariants.
- Enable idempotency for retry-sensitive writes and reuse a stable logical key.
- Run the internal Forge idempotency DB on shared durable storage when multiple application servers must coordinate duplicate prevention.
- Do not cache side-effecting RPCs.

## Cache and Redis

For one worker, memory cache/limiter/realtime can be enough. For multiple workers/servers use Redis for shared cache generations, distributed stampede locks, token buckets and realtime pub/sub.

Recommended high-volume read path:

```text
request → L1 memory → L2 Redis → DB
                   ↘ distributed lock on miss
```

Use short stale windows only for data where temporarily stale reads are acceptable. For balances/purchase state, prefer no stale window or very small TTL plus immediate invalidation.

`fail_open:true` keeps ordinary endpoints alive when cache fails, but it means the DB may receive a sudden load spike. Monitor and capacity-plan for that failure mode.

## Backpressure

`max_concurrent_requests` is not a promise to serve that many DB operations simultaneously. It is a ceiling that prevents unbounded in-process work. Combine it with DB pool limits, request timeout, upstream timeout and rate limiting.

When saturated, fast `503`/`429` responses are healthier than exhausting RAM/file descriptors and crashing every request.

## Media

Use local media only when one node owns the disk and backup/redeployment behavior is understood. For multi-server/high-volume production, implement/use a real S3-compatible object-storage adapter + CDN. The current runtime refuses `backend:"s3"` rather than silently pretending local disk is S3.

Set MIME, extension, file size, batch and owner quota policies. Treat user-supplied filenames as display metadata, never trusted paths.

## Realtime

Memory event hub works only inside one worker. Redis pub/sub is required for worker/server fan-out.

Long-lived WebSockets/SSE fit native ASGI deployment much better than a WSGI/Passenger compatibility bridge. Put Nginx/another reverse proxy in front of Uvicorn/Hypercorn when realtime/high concurrency matters.

## External HTTP sources

Use fixed server-owned target URLs, server-owned secrets, tight timeout/retries and caching where safe. Do not let an untrusted caller choose arbitrary destination URLs.

## Observability

Monitor `/ready`, Prometheus metrics, response latency, 4xx/5xx rates, DB pool saturation, Redis errors, memory, CPU, file descriptors, event-loop stalls and upstream circuit-breaker failures.

The audit writer is bounded and batched so logging cannot grow memory without limit. Decide operationally whether dropping noncritical audit events under extreme overload is acceptable for your regulatory/business requirements.

## cPanel

cPanel/Passenger can serve ordinary HTTP endpoints through `passenger_wsgi.py` + `a2wsgi`. If the provider exposes no Redis/private service networking, keep expectations appropriate for shared hosting. High-volume realtime/media/worker deployments are better on a VPS/container platform with native ASGI and process control.

## Release procedure

```text
1. validate JSON
2. run tests
3. run migrations
4. rotate/load secrets
5. deploy code/config
6. verify /health and /ready
7. verify one authenticated read + one safe write
8. verify metrics/logging
9. monitor error/latency during rollout
```
