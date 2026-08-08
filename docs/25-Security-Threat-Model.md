# Security threat model

This document describes what JSON API Forge v0.4 attempts to protect, which inputs are trusted, and which problems remain the deployment/application owner's responsibility.

Security claims should be evaluated against these boundaries rather than against a vague “secure by default” label.

## Assets

Typical protected assets include:

- database contents;
- API keys and JWT signing material;
- tenant-separated user/application data;
- media objects;
- operation side effects such as balances or inventory;
- internal/external service credentials;
- server availability;
- audit/metrics data.

## Trust boundaries

### Trusted: canonical application configuration

Files under `app/<Project>/` are trusted server configuration. A person who can modify production operation SQL, hook references, roles, or database URLs already has backend-level influence.

Therefore:

- review configuration changes like code;
- protect the repository and deployment pipeline;
- require pull-request review for sensitive fragments;
- never let an untrusted API caller modify operation SQL/config files.

### Untrusted: HTTP/WebSocket clients

Treat all request values as attacker controlled:

- path/query/header/cookie parameters;
- JSON/form/body payloads;
- uploaded filenames/MIME claims;
- API keys/JWTs;
- event payloads;
- external identifiers.

### Trusted-but-risky: Python hooks

Hooks are executable backend code. Declarative safety boundaries do not make an insecure hook secure.

A hook can:

- query another database;
- call external services;
- access files;
- bypass an intended domain rule.

Review/test hooks like ordinary server code.

## Authentication

Forge supports project-scoped API keys plus JWT modes.

### API keys

Use API keys for controlled server/service identities such as:

- Discord bot process;
- Minecraft server/plugin;
- internal service;
- trusted automation.

Prefer one narrow key per integration. Avoid sharing one global `*` key among all plugins.

Do not embed privileged static API keys in browser JavaScript, distributable mobile applications, or downloadable game clients where users can extract them.

### Bootstrap administrator

Bootstrap is provisioning access, not a normal client role.

v0.4 guidance:

- no known/default secret in the repository;
- generate secret with `forge init` or an external secret manager;
- `bootstrap_one_time: true` by default;
- use bootstrap to create a persistent narrow admin key;
- rotate/remove bootstrap provisioning access according to your deployment model.

### JWT

For local HS256, prefer a project-scoped `security.jwt_secret` environment reference and protect that value as a signing key. The global `JWT_SECRET` is a compatibility/shared-infrastructure fallback, not the preferred trust boundary for independent projects. For JWKS, verify issuer/audience/algorithm/claims according to the identity provider's contract.

JWT verification proves token authenticity under the configured trust model; it does not automatically make every claimed role semantically safe. Map external claims intentionally.

## Authorization

### Private by default

RPC operations, custom endpoints, data sources and event channel directions require permissions unless explicitly public.

This protects against omission mistakes such as defining a SQL operation and forgetting its permission.

### Wildcard permissions

Wildcard support is convenient but high privilege:

```text
*
economy.*
notes.*
```

Use wildcard permissions for controlled administrative roles, not every client.

### Tenant isolation

`tenant_field` limits generated SQL/Mongo resource access to the authenticated principal's tenant.

Tenant isolation must be tested for every relevant read/write path. A custom operation/hook that queries the database itself must enforce tenant boundaries explicitly unless its SQL/config naturally does so.

## SQL threat boundary

Declarative SQL operation text is trusted configuration.

Client values are passed through named bind parameters rather than string-concatenated into SQL.

Forge's SQL safety checks can reject suspicious/multi-statement/DDL patterns unless configured, but these checks are **guardrails against operator mistakes, not a parser-level sandbox for hostile SQL**.

Never create an endpoint such as:

```json
{"sql": "$body.sql"}
```

and assume Forge will make arbitrary attacker-provided SQL safe.

## Idempotency threat/reliability boundary

v0.4 binds an idempotency key to a request fingerprint and commits the idempotency result with SQL side effects in the same configured database transaction.

This protects against:

- simple client retries;
- concurrent duplicate key use;
- same key reused for a changed request;
- process failure before the SQL transaction commits.

It does not solve exactly-once behavior across independent systems. External payment APIs, Discord messages, emails, object storage, and another database are not automatically rolled back with your PostgreSQL transaction.

## Rate limiting / DoS

Threats include:

- rotating concrete resource IDs to create buckets;
- generating unbounded in-memory bucket keys;
- long-lived WebSocket message floods;
- concurrent request saturation;
- oversized streamed request bodies.

v0.4 mitigations include:

- principal-global primary rate budget;
- normalized route-template optional budget;
- bounded/expiring in-memory buckets;
- Redis shared limiter option;
- WebSocket message limits;
- bounded concurrency gate;
- ASGI streaming body-size limit.

These are application-layer controls, not volumetric DDoS protection. Use reverse proxies/CDNs/firewalls/provider controls for network-level attacks.

## Cache risks

Incorrect caching can expose data across users/tenants or return stale correctness-sensitive state.

Rules:

- include tenant/principal identity where a response varies by them;
- do not cache authorization decisions carelessly;
- avoid stale-while-revalidate for financial balance/settlement state unless the product explicitly accepts staleness;
- prefer Redis/tiered cache for shared multi-worker state;
- invalidate resource namespaces after writes.

## File/data-source risks

Project-local file sources are constrained to the project directory to reduce path traversal. Writable JSON/YAML uses process/thread coordination plus file locking and atomic replacement.

Limitations:

- local file locking does not make a shared network filesystem universally safe;
- very large file-backed collections are not a replacement for a database;
- public write access is deliberately separate from public read access.

## Media risks

Media controls include size, MIME/extension policy, safe storage keys, metadata, ownership policy and signed temporary reads.

Do not trust client filename or MIME alone for malware/content safety. Production image/video pipelines may need:

- content sniffing;
- antivirus scanning;
- transcoding;
- image re-encoding;
- moderation;
- object-storage quarantine.

These are not all implemented by the v0.4 local media adapter.

## External HTTP data sources

Forge can proxy/gateway an upstream API. Protect upstream secrets in environment variables and define timeouts/retries.

Potential risks:

- SSRF if untrusted users can control the upstream URL;
- retry storms;
- leaking upstream error bodies;
- forwarding sensitive headers/query parameters;
- caching private upstream responses under shared keys.

The upstream URL should be trusted configuration, not arbitrary client input.

## Audit limitations

The built-in audit writer is asynchronous operational telemetry. It uses a bounded queue and may drop events under sustained failure/overflow after retry behavior.

Do not call it a legally durable immutable compliance audit trail without adding a durable architecture appropriate to that requirement.

## Secrets

Never commit:

- `.env`;
- production DB passwords;
- API keys;
- JWT private/signing keys;
- cloud credentials;
- user data dumps.

Use a secret manager in mature deployments. `forge init` is a safe local/bootstrap convenience, not a centralized secrets-management system.

## Reverse proxy / HTTPS

If TLS terminates at a reverse proxy, make sure Forge receives trustworthy proxy information only from infrastructure you control. Do not blindly trust spoofable forwarding headers from the public internet.

`security.require_https=false` can be acceptable behind enforced TLS termination, but `forge doctor --production` warns because Forge cannot prove the external proxy policy.

## Supply chain

Use dependency locking/review appropriate to your deployment. CI includes dependency-graph verification and CodeQL workflow support, but dependency versions and vulnerabilities change over time.

## Security reporting

Follow `SECURITY.md` for private vulnerability reporting. Do not publish a working exploit against current users before the project owner has a reasonable opportunity to investigate and release a fix.

## Non-goals in v0.4

v0.4 does not claim to provide:

- a SQL sandbox for attacker-controlled SQL;
- cross-service distributed transactions;
- volumetric DDoS protection;
- a full WAF;
- malware scanning/transcoding pipeline;
- hardware-backed secret management;
- an immutable compliance ledger;
- automatic business-domain correctness.

Security is strongest when the boundary is explicit.

## Cross-project token isolation

Running multiple apps in one process must not imply that every app shares one identity trust domain. v0.4 disables JWT by default and allows `security.jwt_secret` to reference an app-specific environment secret for local HS256. Prefer separate signing secrets per independent app and keep project-claim validation enabled.

A global `JWT_SECRET` fallback exists for compatibility and current media signed URLs. Treat it as shared infrastructure secret, not as evidence that cross-project bearer trust is desirable. Production diagnostics warn when local JWT verification relies on the shared fallback.

## Media metadata and content validation

Physical storage paths/keys are server internals and should not become an API discovery surface. Forge returns a reduced media DTO and owner-scopes deduplication by default. MIME and extension allow-lists do not prove content safety; untrusted media may still require signature/magic-byte checks, malware scanning and sandboxed decoding before publication.
