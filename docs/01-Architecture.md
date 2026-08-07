# Architecture

JSON API Forge is a **multi-application backend runtime**. The framework code is shared; application behavior lives primarily under `app/<AppName>/`.

## Repository shape

```text
framework/                 reusable runtime
app/
  App1/
    app.json               app identity / root config
    config/*.json          ordered configuration fragments
    data/*                 optional server-owned JSON/YAML/CSV
    hooks/*.py             trusted escape-hatch business logic
  App2/
    ...
clients/                   reusable client SDK examples
examples/                  integration fragments and full examples
docs/                      operator/developer manual
schemas/                   JSON Schemas for editor validation
```

## Runtime layers

1. **ASGI process layer** — FastAPI lifespan, routing, OpenAPI, request/response primitives, health endpoints.
2. **Application discovery layer** — scans `app/*`, reads `app.json`, then deep-merges sorted `config/*.json` fragments.
3. **Protection layer** — project selection, trusted hosts, body limits, concurrency/backpressure, timeout, HTTPS/IP policy and security headers.
4. **Identity/policy layer** — bootstrap admin, project API keys, local JWT or external JWKS JWT, RBAC, tenant binding and per-key traffic budgets.
5. **Declarative API layer** — SQL resources, MongoDB resources, named SQL/RPC operations, data sources, media, realtime channels and custom endpoints.
6. **Data/service layer** — SQLAlchemy async pools, PyMongo async pools, HTTPX connection pool, local media storage and Redis services.
7. **Performance layer** — token-bucket limiting, L1/L2 cache, generation invalidation, stale-while-revalidate and stampede locks.
8. **Consistency layer** — DB transactions, row-count guards and cross-worker idempotency reservations for sensitive RPCs.
9. **Observability layer** — request IDs, readiness, Prometheus metrics and bounded/batched audit writing.
10. **Extension ABI** — trusted Python hooks/dependencies for rules that cannot safely be represented as data.

## Request path

```text
Internet / Discord bot / app / plugin
                 ↓ HTTPS
Reverse proxy / cPanel / Nginx
                 ↓
FastAPI / Forge middleware
  ├─ choose App1/App2
  ├─ body/IP/host/HTTPS protection
  ├─ concurrency backpressure + timeout
  └─ request ID
                 ↓
Authentication
  ├─ bootstrap key (provisioning only)
  ├─ project API key
  └─ JWT: local HS256 or external JWKS
                 ↓
RBAC + tenant + token-bucket budget
                 ↓
Generated endpoint
  ├─ SQL CRUD
  ├─ Mongo CRUD
  ├─ named transactional RPC
  ├─ JSON/YAML/CSV/static/HTTP data source
  ├─ media
  ├─ SSE/WebSocket event channel
  └─ trusted Python hook
                 ↓
Cache / database / storage / upstream service
                 ↓
Response
                 ↘ metrics + bounded audit queue
```

## Isolation model

API keys are stored with a project slug. Cache namespaces include the project slug. Every app owns its own SQL/Mongo aliases, roles, limits, media policy and data-source definitions.

This is **logical isolation inside one Python process**, not an OS sandbox. If two customers must be hostile to each other, deploy separate Forge instances/containers/processes rather than trusting app folders as a security boundary.

## JSON versus Python

JSON is the declarative language. Use it for stable policy and wiring: routes, schemas, permissions, SQL statements, cache rules, data sources, response type, realtime channels and limits.

Python is the extension ABI for business logic that requires code: Discord membership verification, anti-cheat, cryptography, payment provider SDKs, image processing, unusual algorithms, complex branching or third-party libraries.

Never let an untrusted API caller edit app JSON or select arbitrary Python import paths.
