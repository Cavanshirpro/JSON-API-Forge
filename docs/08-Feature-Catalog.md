# Feature catalog and design inventory

This document is the long-term checklist for turning JSON API Forge into a mature reusable backend platform.

## Implemented in this package

### Core/runtime
- FastAPI application factory
- async SQLAlchemy database registry
- normal ASGI startup with Uvicorn
- cPanel Passenger WSGI compatibility bridge
- environment-specific settings
- JSON configuration validation with Pydantic
- environment-variable interpolation in JSON
- generated JSON Schema for editor validation/autocomplete

### Databases
- PostgreSQL/Supabase driver configuration
- MySQL/MariaDB driver configuration
- SQLite development support
- multiple database aliases in one process
- per-resource database routing
- existing-table reflection
- basic JSON-declared table creation

### API generation
- list/read/create/update/delete
- per-resource action enable/disable
- configurable route path
- configurable physical table name
- configurable primary key
- exact-match filters
- sort ascending/descending
- offset/limit pagination
- readable-field allowlists
- writable-field allowlists
- hidden fields
- soft-delete support
- tenant column enforcement for JWT principals
- arbitrary custom hook endpoints declared in JSON

### Security
- bootstrap/root key from environment
- persistent API keys
- plaintext key shown once
- SHA-256 key storage
- key enable/revoke
- key expiration
- roles
- role inheritance
- direct permissions
- wildcard permissions
- action-level permission checks
- JWT bearer verification foundation
- request security headers
- CORS policy

### Abuse/operations
- per-principal/per-path in-memory rate limiting
- Redis distributed rate-limiter option
- request IDs
- request-duration logging
- persistent internal audit records for HTTP requests
- health endpoint
- Swagger/ReDoc/OpenAPI

### Plugin support
- separate API key per plugin
- least-privilege role model
- custom plugin endpoints via Python hooks
- hook access to authenticated principal and database registry

## Recommended next implementation layer

### Configuration language
- split config into `databases.json`, `roles.json`, `resources/*.json`, `endpoints/*.json`
- `$include` and environment overlays (`development`, `production`)
- config inheritance/templates
- config semantic versioning
- hot reload with validation and rollback
- CLI compiler producing one normalized config artifact

### Schema and validation
- JSON Schema request-body definitions per operation
- response schema definitions
- custom validators referenced by dotted Python path
- enum/range/regex validation
- database foreign-key relationship metadata
- typed filter operators
- generated OpenAPI examples

### Data access
- cursor pagination
- joins/relationship expansion
- aggregate endpoints
- batch operations
- transaction groups
- stored procedure/function calls
- read replicas
- database failover policy
- connection-pool tuning per alias
- query timeouts
- optimistic locking/version columns

### Auth/identity
- Supabase Auth JWKS adapter
- generic OIDC/JWKS adapter
- Discord/Google/GitHub OAuth adapters
- refresh token store
- session/device management
- password authentication with Argon2
- email verification/password reset adapters
- API-key tenant binding
- API-key IP/CIDR allowlists
- key rotation/grace periods
- signed service requests

### Authorization
- ABAC expression engine
- ownership rules
- per-field permission maps
- explicit deny rules
- policy priority/order
- resource conditions
- row filters generated from policy

### API governance
- route-level rate limits
- per-key quotas
- monthly usage limits
- plan/tier limits
- idempotency keys
- ETag / If-Match
- API version deprecation dates
- API changelog generation
- generated SDKs
- Postman/Insomnia export

### Events/jobs
- signed outgoing webhooks
- retries and exponential backoff
- webhook delivery history
- Redis/RabbitMQ/Kafka/NATS adapters
- background task queue
- scheduled/cron jobs
- distributed locks
- outbox/inbox patterns
- dead-letter queues

### Files
- multipart upload policies
- local filesystem adapter
- S3-compatible adapter
- Supabase Storage adapter
- signed URLs
- MIME/size restrictions
- antivirus hook
- image processing hooks

### Cache
- declarative cache per endpoint
- Redis cache
- cache keys/scopes
- cache invalidation events
- stale-while-revalidate

### Observability
- Prometheus metrics
- OpenTelemetry tracing
- structured JSON logging
- Sentry/error tracking
- readiness checks per database/Redis/upstream
- audit query/export API
- log redaction rules

### Admin/developer tools
- web admin console
- role editor
- key manager
- usage dashboard
- config editor with schema
- migration dashboard
- plugin registry/manifest
- `forge` CLI
- scaffolding commands
- contract tests generated from config

## Design principle

Do not implement every future feature directly inside the core factory. Mature versions should introduce explicit interfaces such as `DatabaseAdapter`, `IdentityProvider`, `RateLimiter`, `CacheBackend`, `EventBackend`, `StorageBackend` and `PolicyEngine`. JSON should select/configure these components while Python packages implement them.
