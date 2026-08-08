# Production readiness matrix

JSON API Forge v0.4.0 is an Alpha hardening release. This matrix prevents the phrase “production ready” from being applied uniformly to subsystems with different maturity.

Status meanings:

- **Core / recommended with testing** — designed for real use, but validate your workload.
- **Conditional** — useful when deployment assumptions are satisfied.
- **Prototype / limited** — available, but not recommended as authoritative high-scale infrastructure.
- **Documentation/contract only** — configuration/API surface may exist without a complete production adapter.

| Subsystem | v0.4 status | Notes |
| --- | --- | --- |
| Strict JSON/Pydantic config | Core / recommended with testing | Unknown keys fail; JSON Schema generated. |
| Multi-project discovery/merge | Core / recommended with testing | Separate prefixes/policies/runtime objects; review shared process capacity. |
| SQLAlchemy async resources | Core / recommended with testing | PostgreSQL/MySQL/SQLite drivers; production DB/index/migration design remains operator responsibility. |
| PostgreSQL | Core / recommended with testing | Preferred for transactional/concurrent authoritative workloads. |
| MySQL/MariaDB | Conditional | Async driver supported; ensure integration coverage for your exact version/topology. |
| SQLite | Conditional | Strong local/small workload option; evaluate concurrency/durability before production. |
| SQL/RPC operations | Core / recommended with testing | Trusted config + bind params + transaction/row guards. SQL guardrail is not hostile-SQL sandbox. |
| Same-DB idempotency | Core / recommended with testing | Atomic with configured SQL transaction and request fingerprint; does not cover external side effects. |
| API keys/RBAC | Core / recommended with testing | Narrow keys recommended; bootstrap one-time by default. |
| Local HS256 JWT | Conditional | Secure only with strong secret/rotation/claim policy. |
| JWKS JWT | Conditional | Depends on provider config, issuer/audience/claim mapping and network availability. |
| Tenant fields | Core / recommended with testing | Applies to generated resource paths; custom SQL/hooks must preserve tenant boundaries themselves. |
| Memory cache | Conditional | One process only; bounded local optimization. |
| Redis cache | Core / recommended with testing | Preferred for shared cache; plan failure/load behavior. |
| Tiered L1 + Redis L2 cache | Conditional | Useful at scale; stale/invalidation semantics must match data correctness needs. |
| Memory rate limiting | Conditional | Per process; bounded/expiring. |
| Redis rate limiting | Core / recommended with testing | Shared token bucket; use for multi-worker enforcement. |
| Concurrency gate/body limit | Core / recommended with testing | Application-layer overload protection; not network DDoS protection. |
| Async audit writer | Conditional | Operational telemetry; not immutable compliance ledger. |
| JSON/YAML writable data source | Prototype / limited | Local small-data use; locking + atomic replace, not distributed high-write DB. |
| CSV data source | Prototype / limited | Read-oriented simple datasets. |
| HTTP upstream data source | Conditional | Timeouts/retries/circuit behavior; protect upstream secrets and SSRF boundary. |
| MongoDB resources | Conditional | PyMongo async; use real service integration tests for deployment version. |
| SSE | Conditional | Native ASGI recommended; proxy/timeouts matter. |
| WebSocket | Conditional | Message limits/queues/rate limits; native ASGI required for serious realtime. |
| Memory realtime | Prototype / limited | Single worker only. |
| Redis realtime | Conditional | Cross-worker pub/sub; not a durable message queue/history. |
| Local media storage | Prototype / limited for horizontal scale | Suitable single host; monitor disk/backup. |
| Object-storage media adapter | Not implemented in v0.4 | Use the local backend only within its documented single-host/shared-disk limits; add a real tested object-storage adapter before horizontal media scale. |
| Messaging/social/gaming packs | Prototype / starter | Schema/resource accelerators, not complete domain products. |
| Python reference client | Core reference | Async HTTPX client; app still owns retry/security policy. |
| TypeScript reference client | Core reference | Fetch-based client; do not put privileged static keys in untrusted clients. |
| cPanel Passenger HTTP | Conditional | REST/normal HTTP compatibility; WSGI bridge is not the preferred realtime path. |
| Dockerfile/Compose example | Conditional | Reproducible example, not a managed production platform. |

## Workload recommendations

### Good v0.4 evaluation targets

- Discord bot backend;
- Minecraft/plugin service;
- internal API;
- small SaaS MVP;
- game backend prototype/control service;
- multi-app VPS backend;
- admin/integration API.

### Require stronger independent validation

- payment settlement;
- wallet/financial ledger;
- critical identity provider;
- very high-volume public API;
- regulated immutable audit system;
- zero-data-loss storage service;
- large messaging/realtime platform.

The fact that Forge contains an economy example does not mean every financial workload inherits a certification or correctness guarantee.

## Promotion criteria for stronger maturity

A subsystem should move toward a stronger maturity label only after evidence such as:

- sustained green CI across supported Python versions;
- real service integration coverage;
- >=80% critical-path coverage for security/reliability code, not only aggregate coverage;
- concurrency/failure tests;
- production case studies;
- migration/backup/restore validation;
- independent security review for high-risk claims;
- documented operational limits.

## Why the matrix exists

JSON API Forge has a broad surface. Without a matrix, documentation can accidentally imply that “implemented” equals “equally mature.” v0.4 explicitly avoids that claim.

The development priority after v0.4 should continue to be evidence and reliability on the core before broadening feature packs again.

## v0.4 verification posture

The repository now enforces a 75% aggregate branch-aware coverage floor plus file-specific critical floors: >=80% for high-risk runtime modules and >=75% for the generated project-router assembly surface. Factory and runtime lifecycle code are included in the critical gate so orchestration cannot hide behind high utility-code coverage. This is meaningful evidence, but it is **not equivalent to production certification**; deployment-specific behavior and live infrastructure still require CI/service tests and operator validation.

The release therefore remains Alpha until the exact release commit is green on the supported Python matrix and the PostgreSQL/Redis/MongoDB live-service job, TypeScript typecheck and container build gates are all green. Local skips caused by unavailable services must never be described as passed integrations.
