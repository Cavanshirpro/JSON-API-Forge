# Architecture

## Layers

1. **Process/runtime layer** — FastAPI/ASGI, lifecycle, health/readiness and middleware.
2. **Project discovery layer** — scans `app/*`, loads each `app.json`/`manifest.json`, then merges ordered JSON fragments.
3. **Policy layer** — authentication, RBAC, per-action permissions, IP policy, HTTPS policy, request limits and rate limits.
4. **API generation layer** — turns resource definitions into CRUD routes and feature-pack resources.
5. **Service layer** — media storage, cache, outbound HTTP clients and future queue/search/storage adapters.
6. **Data layer** — one or more async SQLAlchemy engines per project, each with independent connection-pool settings.
7. **Observability layer** — request IDs, access logs, readiness probes and a non-blocking batched audit queue.
8. **Extension layer** — small Python hooks for business rules that should not be represented as blind JSON CRUD.

## Multi-project isolation

Each project has a unique `slug` and `api_prefix`. API keys are scoped to the project slug in the internal security database. Cache namespaces include the project slug. Resource tables and database engines are held inside a per-project runtime object.

The framework still shares one Python process. If you need hard process/security isolation between customers, deploy separate Forge instances rather than treating project folders as a sandbox.

## Request path

```text
reverse proxy / cPanel
        ↓
ASGI/WSGI bridge
        ↓
project-aware protection middleware
        ↓
authentication → token-bucket rate limit
        ↓
cache lookup (GET)
        ↓
resource/hook/media service
        ↓
async DB / storage
        ↓
cache generation bump (mutation)
        ↓
response
        ↘ bounded audit queue → batched DB writes
```
