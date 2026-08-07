# Production scaling

## Single cPanel process

Use memory cache/limiter for simple installations. PostgreSQL is preferred over SQLite for meaningful concurrency.

## Multiple workers

Move cache and rate limiting to Redis. Ensure all workers point to the same internal security DB and Redis. Calculate total DB pool connections before increasing worker count.

## Horizontal scaling

For more than one web host:

- load balancer / reverse proxy
- multiple ASGI workers
- PostgreSQL/MySQL with suitable pooling or external pooler
- shared Redis
- S3-compatible media storage + CDN
- queue workers for slow jobs
- centralized logs/metrics/traces

## Hot paths

Cache stable reads, paginate lists, index all common filters/order fields, avoid N+1 queries, move slow external calls behind resilient clients/queues, and never do media conversion in the request path.

## Failure containment

Backpressure and request timeouts stop overload from becoming process collapse. The outbound HTTP helper implements connection pooling, retry/backoff and a circuit breaker so an unhealthy dependency does not consume every request worker indefinitely.

## Recommended next production modules

The current runtime is deliberately modular. High-scale deployments should add adapters for Prometheus/OpenTelemetry, distributed jobs (Celery/Arq/Dramatiq), S3/CDN, Alembic migration orchestration and optional distributed stampede locks.
