# Security and protection

## Identity types

Forge supports three primary caller models.

**Bootstrap administrator** is a provisioning credential loaded from the environment. v0.4 ships no usable default bootstrap secret; create one with `forge init` or a secret manager. Bootstrap is one-time by default and should only provision ordinary admin/service keys. Never ship it to a client/plugin.

**Project API key** is ideal for Discord bots, Minecraft plugins, cron jobs and server-to-server integrations. Keys are stored only as SHA-256 hashes and can have roles, direct permissions, tenant binding, expiration and per-key traffic budgets.

**Bearer JWT** is ideal for end users. `jwt_provider:"local_hs256"` uses Forge-issued JWTs. `jwt_provider:"jwks"` validates tokens from an external issuer such as Supabase using cached JWKS signing keys.

## Least-privilege API keys

A Discord economy bot should receive:

```json
{
  "roles":["economy_bot"],
  "permissions":[],
  "rate_requests":600,
  "rate_window_seconds":60,
  "rate_burst":120
}
```

It should **not** receive a PostgreSQL password or `*` permission.

## RBAC

Roles can inherit roles; permissions use dotted names and wildcard matching:

```text
economy.balance.read
economy.transfer
media.upload
social.posts.read
social.*
*
```

The route asks for a permission; Forge expands the caller's roles and checks the resulting set.

## Tenant isolation

For SQL/Mongo resources with `tenant_field`, Forge requires `principal.tenant_id` and injects tenant constraints into reads/writes. API keys can be permanently bound to a tenant. JWT claims can be mapped to a tenant claim.

Tenant filters are a useful defense, but application-domain authorization still matters. For example, a Discord user must not be allowed to claim another user's ID merely because both are in the same tenant.

## JWT/JWKS checks

JWKS mode verifies the token signature with an allowed algorithm and can verify configured issuer/audience. Signing keys are cached and refreshed once when an unknown `kid` appears, which supports normal key rotation without fetching the JWKS endpoint on every request.

Dotted claim paths can map identity-provider metadata into Forge:

```json
{
  "jwt_roles_claim":"app_metadata.roles",
  "jwt_permissions_claim":"app_metadata.permissions",
  "jwt_tenant_claim":"app_metadata.tenant_id"
}
```


## Project-scoped local JWT signing

JWT is **disabled by default** in v0.4. Enable it only for projects that actually need bearer authentication. For local HS256, prefer a project-specific secret rather than sharing one signing key across every app:

```json
{
  "security": {
    "jwt_enabled": true,
    "jwt_provider": "local_hs256",
    "jwt_secret": "$env:APP1_JWT_SECRET"
  }
}
```

`forge init` discovers this environment reference and generates the secret. A global `JWT_SECRET` is retained as a compatibility fallback and is also used by the current local-media signed-URL implementation, but `forge doctor --production` warns when a local JWT project depends on that shared fallback.

Project-scoped signing limits accidental trust expansion: a token signed for App1 cannot be validated merely because App2 happens to use local JWT as well. Keep the project claim check enabled and use separate keys whenever applications have different trust boundaries.

## Request protections

Project JSON can control request body limit, maximum concurrent requests, timeout, queue wait, gzip threshold, Trusted Host values, CORS origins, optional HTTPS enforcement and IP allow/deny CIDRs.

When saturated, rejecting quickly with `503` is safer than allowing an unbounded request queue to consume memory until the process dies.

## Rate limiting

The token-bucket limiter supports memory or Redis. The primary bucket is **principal-global** rather than based on the concrete request path, preventing callers from rotating resource IDs to create unlimited primary buckets. An optional second route-template budget can protect expensive endpoint families.

In-memory limiter state has an idle TTL, periodic cleanup and a maximum bucket count. Use Redis when several workers/servers must enforce one shared budget. A key can override the project default with its own `rate_requests`, `rate_window_seconds` and `rate_burst`. WebSocket event channels may additionally define per-message budgets.

## Idempotency for money/purchases

v0.4 stores an idempotency record in the **same configured business database transaction** as an idempotent SQL/RPC operation. The logical idempotency identity is bound to a request fingerprint; the same key with a changed payload is rejected instead of replaying an unrelated result. Business side effects and the completed response record commit together.

This removes the v0.3 crash window between business commit and a separate idempotency completion write. It does **not** provide cross-system exactly-once delivery for external payment APIs, Discord messages, email, object storage or a second database. Those flows require provider idempotency, an outbox/inbox, a durable queue or compensating design.

Use stable logical IDs such as a Discord interaction ID, payment-provider event ID or order ID. Generating a different random key for every retry defeats idempotency.

## SQL safety boundary

Clients never submit raw SQL by default. Named operations contain server-owned SQL and use bind parameters. The RPC engine rejects multiple statements/comments, restricts read modes and disables DDL/administrative verbs unless explicitly allowed.

Parameter binding prevents values such as usernames or amounts from becoming SQL syntax. It does not magically make a poorly designed operation safe; permissions and domain invariants still matter.

## Secrets

Keep DB URLs, bootstrap keys, upstream tokens, JWT secrets and Redis credentials in environment variables. Never put them in mobile binaries, Discord plugins, browser JavaScript or public Git repositories.


## Secure-by-default endpoint declarations

Declarative SQL operations, custom endpoints, data sources and event channel directions are private by default. A configuration must name a permission or explicitly opt into public access. Data-source `public` affects reads only; public mutations require the separate `public_write:true` opt-in. This rule exists so forgetting a permission cannot silently create an anonymous SQL/data endpoint.

## Request-size and saturation protection

The request-body limit is enforced while ASGI chunks are received, not only by trusting `Content-Length`. `reject_when_saturated:true` rejects excess concurrent work quickly; when false, waiting is still bounded by `max_queue_wait_seconds`. These are application-layer controls and do not replace reverse-proxy/network DDoS protection.

## One-time bootstrap concurrency semantics

When `bootstrap_one_time=true`, the bootstrap credential is intended only to create the first durable administrative API key. v0.4 performs bootstrap consumption and that API-key insert in the **same internal-database transaction**.

This matters under concurrency. Two requests may authenticate with the bootstrap secret at nearly the same instant, but the durable mutation path uses a locked/bootstrap-state record (or a primary-key race for the first state row). Only one transaction can commit the bootstrap consumption plus key insert. The losing request is rolled back and receives `401` rather than creating a second key.

Operational consequences:

- do not use the bootstrap key as a normal long-lived administrator credential;
- create a narrow persistent administrator key once, then store/rotate it through your secret-management process;
- back up the internal Forge metadata database if losing API-key/bootstrap/media metadata would be disruptive;
- do not manually delete/reset `_forge_v4_bootstrap_state` in production as a routine recovery mechanism;
- if emergency bootstrap recovery is required, treat it as a privileged operational procedure and rotate the bootstrap secret immediately afterward.
