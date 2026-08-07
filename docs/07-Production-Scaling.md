# Production scaling

## Stage 1 — one process

For a small HTTP API:

```text
FastAPI/Passenger bridge
  ├─ memory cache
  ├─ memory limiter
  └─ PostgreSQL/MySQL
```

SQLite is useful for development; meaningful concurrent writes should move to a server database.

## Stage 2 — multiple processes

Use shared state:

```text
workers
  ├─ PostgreSQL/MySQL
  └─ Redis
       ├─ cache L2 / generations
       ├─ distributed cache lock
       ├─ token bucket rate limit
       └─ realtime pub/sub
```

All processes must use the same internal security/audit DB if API keys are expected to work everywhere.

## Stage 3 — multiple machines

Typical shape:

```text
CDN/WAF/load balancer
        ↓
ASGI web nodes
  ├─ PostgreSQL / managed SQL / pooler
  ├─ Redis cluster/service
  ├─ MongoDB when configured
  ├─ object storage/CDN
  └─ durable workers/queues for slow jobs
```

## Realtime

Forge includes memory and Redis event hubs. Redis allows WebSocket/SSE publishers and subscribers on different workers to see the same channel.

Transport still matters: cPanel's WSGI compatibility bridge is not the preferred deployment for serious WebSocket traffic. Native ASGI should be used for realtime workloads.

## Hot path rules

- Reuse DB and HTTP pools.
- Cache stable reads.
- Index filter/sort fields.
- Prefer cursor pagination for deep streams.
- Keep SQL RPC results bounded.
- Keep expensive Python hooks off hot list endpoints.
- Move heavy media processing to workers.
- Never create one DB connection or one `AsyncClient` per request.
- Use idempotency on retry-sensitive writes.

## Metrics

`/metrics` exposes Prometheus-format request counter/latency metrics when enabled. `/health` proves the process is alive; `/ready` actively checks configured SQL databases.

Production monitoring should additionally cover Redis, MongoDB, DB pool exhaustion, queue depth, process RAM/CPU, 429/503/5xx rates, p95/p99 latency and storage usage.

## Local load probe

A small HTTP concurrency probe is included:

```bash
python scripts/load_test.py \
  https://api.example.com/api/app1/v1/rpc/economy.balance/123 \
  --requests 10000 \
  --concurrency 100 \
  --api-key 'jf2_...'
```

It prints status counts, approximate RPS and p50/p95/p99 latency. Start with reads, then use a disposable test database for write benchmarks. Do not aim a write load test at real economy/payment data.

For serious capacity work, also use a distributed tool and monitor DB/Redis/process metrics while the load runs; client-side RPS alone cannot identify the bottleneck.
