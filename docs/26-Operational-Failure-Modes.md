# Operational failure modes

A backend should define what happens when dependencies are slow, unavailable, or overloaded. This document is an operator-focused map of expected v0.4 behavior.

## PostgreSQL/MySQL unavailable

Generated SQL resources and operations that require the database will fail. `/ready` attempts a simple query and should report degraded readiness.

Recommended behavior outside Forge:

- remove an unready instance from load balancing;
- alert on DB connectivity/pool exhaustion;
- avoid infinite application retries;
- preserve a tested backup/restore procedure.

Forge DB pools use async SQLAlchemy engines and configurable pool settings for non-SQLite databases.

## Connection pool saturation

Symptoms:

- increasing latency;
- pool timeout errors;
- request timeout/503/5xx depending on where saturation appears;
- database connection pressure.

Do not simply increase pool size on every worker. Total possible DB connections are roughly a topology problem:

```text
workers × per-worker pool + overflow
```

and must fit the database's actual safe connection capacity.

## Redis unavailable: cache

If cache `fail_open` is enabled, a cache failure can fall through to the database depending on the operation path. This preserves availability but increases DB load.

Operational consequence: losing Redis can become a database traffic spike. Capacity planning must account for this failure mode.

## Redis unavailable: rate limiter

Rate limiter `fail_open` is a security/availability policy choice.

- fail-open: traffic continues without the intended shared limit;
- fail-closed: requests fail with a temporary-unavailable response.

For expensive or abuse-sensitive endpoints, fail-closed can be safer. For low-risk public read APIs, fail-open can preserve availability.

## Redis unavailable: realtime

Redis-backed realtime cannot fan events across processes/servers when Redis is unavailable. `/ready` reports shared service health through the runtime service ping path.

Clients should reconnect with backoff rather than tight loops.

## In-memory cache/rate/realtime in multiple workers

Each worker has separate process memory.

Consequences:

- memory rate limits are per process;
- memory realtime does not cross workers;
- memory cache contents differ between workers.

Use Redis where consistency across workers matters.

## Cache stampede

When a hot key expires, many requests can try to load the same backing data.

Forge's cache manager uses local single-flight behavior and can use distributed Redis locking for cross-worker mitigation.

No lock mechanism eliminates every failure mode. Use short DB queries/indexes and capacity planning so the database survives a cache miss storm.

## Stale-while-revalidate

Stale data can improve availability/latency for feeds/catalogs. It can be wrong for balances, authorization, settlement or inventory ownership.

Set `stale_ttl_seconds=0` for correctness-sensitive data unless stale behavior is explicitly part of the product contract.

## Audit queue saturation

The audit writer intentionally uses a bounded queue to prevent audit telemetry from causing unbounded memory growth.

When the queue is full:

- events can be dropped;
- a dropped counter is incremented;
- metrics/logging should expose pressure.

Transient database failures are retried with bounded backoff. A final write failure is observable, but the built-in writer is still best-effort telemetry.

If every audit record must be durable, send events to a durable queue/append-only system designed for that guarantee.

## Request concurrency saturation

`max_concurrent_requests` limits concurrent requests per project runtime gate.

If `reject_when_saturated=true`, excess work is rejected rather than queued indefinitely.

If false, requests may wait only up to `max_queue_wait_seconds`.

A bounded queue prevents “accept everything until memory dies,” but clients must handle temporary failures and retry with jitter when appropriate.

## Request timeout

`request_timeout_seconds` limits the middleware-wrapped request execution window.

Timeout does not necessarily cancel an external side effect that has already reached another service. For critical workflows, understand cancellation behavior of the dependency and use idempotency/transaction patterns.

## Oversized request body

ASGI body middleware counts incoming chunks and rejects payloads above the project limit.

Media endpoints also have separate upload limits. Set both according to your product needs and reverse-proxy limits.

The reverse proxy should generally reject oversized uploads before they consume application resources when possible.

## Idempotent operation conflict

Same idempotency key + different request fingerprint returns a conflict. This is a client bug or misuse, not a signal to retry blindly with the same key.

A `pending` conflict can occur under concurrent duplicate requests; a client may retry later with the same request/key using bounded backoff.

## SQL operation rollback

Transactional operations execute their statements in one SQL transaction. Row-count requirements and statement failures roll back the transaction.

A side effect performed by a Python hook/external provider outside that DB transaction is not rolled back automatically.

## External HTTP upstream unavailable

The resilient HTTP client/data source applies configured timeout/retry/backoff/circuit behavior.

Rules:

- keep timeouts finite;
- retry only operations safe to retry;
- use upstream idempotency for non-idempotent writes;
- avoid multiplying retries at proxy + Forge + upstream layers;
- monitor circuit-open events.

## MongoDB unavailable

Mongo resource requests fail and readiness should degrade when Mongo is configured/active. Use driver pool/timeouts appropriate to the topology.

## File-backed data source contention

Writable JSON/YAML sources use async coordination, cross-process file locks and atomic replace on the host.

They are intended for small data/config/catalog-style workloads, not high-write distributed databases.

Failure considerations:

- lock timeout;
- disk full;
- permissions;
- network filesystem semantics;
- process crash around filesystem operations.

Use PostgreSQL/MongoDB for high-write/concurrent authoritative data.

## Local media disk full

Local media upload can fail if the filesystem is full or read-only. Monitor disk space/inodes and keep media on a volume with backup/retention policy.

Local media is not shared across hosts. Horizontal deployments require shared object storage or equivalent architecture. v0.4 intentionally exposes only the implemented `local` media backend; object-storage values are not valid configuration until an adapter actually exists and is tested.

## WebSocket overload

Controls include:

- connection/global rate limit;
- per-message rate limit;
- maximum message bytes;
- per-subscriber queue size.

Slow subscribers can still affect experience. Design client reconnect/backpressure behavior and prefer a dedicated realtime architecture if the product becomes messaging-heavy.

## Graceful shutdown

Runtime shutdown closes project services and the audit writer. Container/orchestrator shutdown grace periods should be long enough for the application to stop accepting new work and close resources.

Do not assume every external side effect can be safely interrupted at any instruction boundary.

## Health vs readiness

`/health` means the process/runtime is alive enough to answer.

`/ready` checks configured dependencies and can return degraded/unavailable.

Load balancers should use readiness for traffic decisions and health/liveness for restart decisions according to infrastructure policy.

## Failure-testing checklist

Before calling a workload production-ready, deliberately test:

- DB unavailable for 30 seconds;
- Redis unavailable with cache fail-open;
- Redis unavailable with limiter fail-closed;
- worker killed during idempotent DB operation;
- upstream HTTP timeout;
- disk full/permission error for local file/media;
- request concurrency beyond the gate;
- oversized chunked body;
- repeated WebSocket messages above the channel budget;
- shutdown with queued audit events;
- tenant-crossing attack requests.

Reliability is a behavior under failure, not only a successful happy-path request.


## Upstream retry amplification

Retry policy is part of correctness, not only availability. Retrying a non-idempotent upstream mutation can duplicate a charge/order/message. Forge therefore avoids automatic POST/PATCH retries unless `retry_non_idempotent:true` is explicit. Even with that flag, the operator must provide the upstream idempotency mechanism. Monitor repeated `429`/`5xx`, circuit-open errors and upstream latency rather than increasing retry counts blindly; retries multiply load during incidents.

## Redis realtime listener startup failure

A Redis event listener is not considered ready until the subscription has been acknowledged. A subscription task that fails before readiness is surfaced immediately. Clients should still use bounded reconnect backoff because a dependency outage can persist beyond one request.

## Cache stale-refresh failure

Stale-while-revalidate work runs outside the caller's critical path. A refresh failure leaves the previously stale value subject to its configured stale window, records/logs the refresh error, and clears the in-flight refresh marker so a later request can try again. Single-flight lock entries are removed when no waiter/user remains; they are not intended to grow forever with historical cache keys.

## Media metadata persistence failure

For local storage, Forge deletes the just-written file if the subsequent metadata insert fails. This narrows the ordinary orphan-file window. A process kill, disk failure or administrator filesystem modification can still require reconciliation tooling/backups; local disk is not a transactional object store.
