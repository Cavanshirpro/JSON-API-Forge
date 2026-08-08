# JSON API Forge documentation

The documentation is intentionally **progressive**. A new user should be able to create and call one API without first understanding every subsystem; operators and framework contributors can then move into the security, consistency and failure-mode material.

## Recommended reading paths

### New user — one API running

1. [`00-Start-Here.md`](00-Start-Here.md)
2. [`02-Multi-Project-Configuration.md`](02-Multi-Project-Configuration.md)
3. [`13-JSON-Language-Reference.md`](13-JSON-Language-Reference.md)
4. [`22-CLI-and-Developer-Experience.md`](22-CLI-and-Developer-Experience.md)
5. [`24-JSON-Schema-and-IDE-Setup.md`](24-JSON-Schema-and-IDE-Setup.md)

### Bot / Discord economy backend

1. [`08-Discord-Economy-and-PostgreSQL.md`](08-Discord-Economy-and-PostgreSQL.md)
2. [`09-RPC-and-SQL-Operations.md`](09-RPC-and-SQL-Operations.md)
3. [`17-Transactions-Idempotency-and-Consistency.md`](17-Transactions-Idempotency-and-Consistency.md)
4. [`29-Row-Ownership-and-Authorization.md`](29-Row-Ownership-and-Authorization.md)
5. [`35-Credential-Delegation-JWT-and-Operator-Trust.md`](35-Credential-Delegation-JWT-and-Operator-Trust.md)

### Production operator

1. [`14-Operations-and-Production-Checklist.md`](14-Operations-and-Production-Checklist.md)
2. [`30-Database-Schema-Lifecycle-and-Migrations.md`](30-Database-Schema-Lifecycle-and-Migrations.md)
3. [`31-Reverse-Proxy-Trust-TLS-and-Client-IP.md`](31-Reverse-Proxy-Trust-TLS-and-Client-IP.md)
4. [`38-Operational-Endpoints-Metrics-and-Readiness.md`](38-Operational-Endpoints-Metrics-and-Readiness.md)
5. [`40-Rate-Limiting-Overload-and-High-RPS.md`](40-Rate-Limiting-Overload-and-High-RPS.md)
6. [`26-Operational-Failure-Modes.md`](26-Operational-Failure-Modes.md)
7. [`27-Production-Readiness-Matrix.md`](27-Production-Readiness-Matrix.md)
8. [`41-Known-Limits-and-Non-Goals.md`](41-Known-Limits-and-Non-Goals.md)

### Security reviewer

1. [`04-Security-and-Protection.md`](04-Security-and-Protection.md)
2. [`25-Security-Threat-Model.md`](25-Security-Threat-Model.md)
3. [`29-Row-Ownership-and-Authorization.md`](29-Row-Ownership-and-Authorization.md)
4. [`31-Reverse-Proxy-Trust-TLS-and-Client-IP.md`](31-Reverse-Proxy-Trust-TLS-and-Client-IP.md)
5. [`35-Credential-Delegation-JWT-and-Operator-Trust.md`](35-Credential-Delegation-JWT-and-Operator-Trust.md)
6. [`37-Outbound-HTTP-and-Egress-Security.md`](37-Outbound-HTTP-and-Egress-Security.md)

### Framework maintainer / release reviewer

1. [`23-Testing-CI-and-Reliability.md`](23-Testing-CI-and-Reliability.md)
2. [`28-v0.4-Verification-Report.md`](28-v0.4-Verification-Report.md)
3. [`34-Senior-Engineering-Review-and-Release-Gates.md`](34-Senior-Engineering-Review-and-Release-Gates.md)
4. [`36-Configuration-Merge-Semantics.md`](36-Configuration-Merge-Semantics.md)
5. [`41-Known-Limits-and-Non-Goals.md`](41-Known-Limits-and-Non-Goals.md)

## Core architecture and configuration

| Document | Purpose |
| --- | --- |
| `00-Start-Here.md` | Five-minute path from clone/install to a generated API. |
| `01-Architecture.md` | Runtime boundaries, lifecycle and data flow. |
| `02-Multi-Project-Configuration.md` | `app/App1`, fragment loading and project isolation. |
| `03-Performance-and-Cache.md` | Tiered cache, invalidation, pools and scaling. |
| `04-Security-and-Protection.md` | Authentication, RBAC, tenant/security controls. |
| `13-JSON-Language-Reference.md` | Declarative configuration reference. |
| `24-JSON-Schema-and-IDE-Setup.md` | Schema generation and editor integration. |
| `29-Row-Ownership-and-Authorization.md` | Row ownership, tenant boundaries and bypass policy. |
| `36-Configuration-Merge-Semantics.md` | Append-vs-replace fragment semantics and secret resolution. |

## API surfaces and integrations

| Document | Purpose |
| --- | --- |
| `05-Media.md` | Local media, quotas, signed URLs and metadata. |
| `06-Messaging-Social-Gaming.md` | Optional secure schema/resource primitives. |
| `08-Discord-Economy-and-PostgreSQL.md` | End-to-end bot → Forge → SQL flow. |
| `09-RPC-and-SQL-Operations.md` | Trusted declarative SQL/RPC operations. |
| `10-Data-Sources-and-API-Gateway.md` | JSON/YAML/CSV/static/HTTP sources. |
| `11-FastAPI-Declarative-Features.md` | Parameters, schemas, dependencies, response types, WebSocket/SSE/OpenAPI. |
| `12-Client-SDK-and-Plugins.md` | Python/TypeScript clients and plugin credentials. |
| `15-MongoDB.md` | MongoDB resource adapter. |
| `16-Supabase-Auth-and-PostgreSQL.md` | PostgreSQL/JWKS integration pattern. |
| `17-Transactions-Idempotency-and-Consistency.md` | Transaction/idempotency guarantees and boundaries. |
| `18-Recipes-and-Decision-Guide.md` | Pattern selection by workload. |
| `19-Generated-Endpoint-Map.md` | Generated endpoint families. |
| `32-API-Semantics-and-HTTP-Contracts.md` | PATCH/PUT, pagination, status codes and cache metadata. |
| `33-Realtime-Delivery-and-Backpressure.md` | SSE/WebSocket delivery and bounded slow-client behavior. |
| `37-Outbound-HTTP-and-Egress-Security.md` | HTTP gateway trust, SSRF guardrails and retries. |
| `39-Media-Consistency-Quotas-and-Batch-Semantics.md` | Media transactional boundaries and batch behavior. |

## Operations, hardening and release evidence

| Document | Purpose |
| --- | --- |
| `07-Production-Scaling.md` | Multi-worker/multi-node deployment considerations. |
| `14-Operations-and-Production-Checklist.md` | Operator checklist. |
| `21-v0.4-Hardening-and-Migration.md` | v0.3 → v0.4 security/reliability changes. |
| `22-CLI-and-Developer-Experience.md` | `forge` commands, presets and initialization. |
| `23-Testing-CI-and-Reliability.md` | Test pyramid, service containers and coverage gates. |
| `25-Security-Threat-Model.md` | Threat model and security non-goals. |
| `26-Operational-Failure-Modes.md` | Dependency failure behavior. |
| `27-Production-Readiness-Matrix.md` | Subsystem maturity and production guidance. |
| `28-v0.4-Verification-Report.md` | Exact local verification evidence and CI boundary. |
| `30-Database-Schema-Lifecycle-and-Migrations.md` | Explicit migration vs runtime DDL. |
| `31-Reverse-Proxy-Trust-TLS-and-Client-IP.md` | Proxy/CDN trust boundary and TLS/client IP. |
| `34-Senior-Engineering-Review-and-Release-Gates.md` | Release-blocking engineering questions/checks. |
| `35-Credential-Delegation-JWT-and-Operator-Trust.md` | Delegation containment and auth-cache revocation semantics. |
| `38-Operational-Endpoints-Metrics-and-Readiness.md` | `/health`, `/ready`, `/metrics`, operator trust. |
| `40-Rate-Limiting-Overload-and-High-RPS.md` | Pre-auth/principal/route limits and overload design. |
| `41-Known-Limits-and-Non-Goals.md` | Explicit boundaries and non-goals. |
| `cPanelGuide.md` | Passenger HTTP deployment and native-ASGI limitations. |

## Upgrade documents

- [`20-Upgrading-from-v0.2.md`](20-Upgrading-from-v0.2.md)
- [`21-v0.4-Hardening-and-Migration.md`](21-v0.4-Hardening-and-Migration.md)

## Documentation rule

Documentation is part of the runtime contract. It must describe **verified current behavior**, not roadmap behavior. A backend, CLI switch, security guarantee or test result that is not implemented/verified must not be presented as available.
