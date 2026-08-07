# Future feature map

The current package focuses on a safe, runnable core. The architecture intentionally leaves room for these additions without rewriting application configs.

## Identity and auth adapters

- Supabase Auth JWT verification (JWKS)
- Google / GitHub / Discord OAuth2/OIDC
- password login with Argon2
- refresh-token rotation and revocation
- service accounts
- mTLS identity

## API key improvements

- per-key tenant binding
- IP/CIDR allowlists
- per-key expiration/rotation workflow
- key groups/environments
- usage counters and billing quotas
- separate read/write quotas
- signed requests (HMAC) for high-trust server integrations

## Authorization

- ABAC conditions (`owner_id == principal.sub`)
- row-level policy expressions
- field-level permissions by role
- deny rules with precedence
- time-window permissions

## API behavior

- cursor pagination
- richer typed filters (`gt`, `gte`, `in`, `contains`, date ranges)
- sparse fieldsets
- relationship expansion
- batch CRUD
- idempotency keys
- optimistic concurrency / ETags
- request schemas generated from JSON Schema
- response schemas and examples
- API deprecation metadata
- per-resource versioning

## Reliability

- Redis distributed rate limiter
- Redis cache
- circuit breakers
- retries with exponential backoff
- request timeout budgets
- background jobs (Celery/Dramatiq/Arq)
- dead-letter queue
- scheduled jobs
- outbox pattern

## Events/integrations

- outgoing webhooks with signing/retry
- event bus adapters (Redis Streams, RabbitMQ, Kafka, NATS)
- webhook subscriptions stored per client/plugin
- inbound webhook verification adapters

## Data

- Alembic migration generation
- seed data
- encrypted columns
- file/object-storage resources (S3/Supabase Storage)
- MongoDB and Elasticsearch adapters
- transaction groups defined by hooks

## Observability

- structured JSON logs
- persistent audit log
- Prometheus `/metrics`
- OpenTelemetry traces
- Sentry integration
- health/readiness/liveness per dependency
- slow-query logging

## Administration

- admin UI
- key creation/revocation screen
- role/permission editor
- live config validation
- config hot reload with safe rollback
- API usage dashboard
- audit search/export

## Developer experience

- `forge init`, `forge validate`, `forge key create` CLI
- JSON Schema/autocomplete for config
- config split/merge (`resources/*.json`)
- generated SDKs (Python, TS, C#, Java, C++) from OpenAPI
- generated Postman/Insomnia collections
- plugin SDK
- testing fixtures and contract tests

These are intentionally listed as a roadmap instead of being stubbed as fake production-ready features.
