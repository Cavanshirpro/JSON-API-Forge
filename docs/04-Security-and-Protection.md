# Security and protection

## Identity types

Forge supports three primary caller models.

**Bootstrap administrator** is a provisioning credential loaded from the environment. It should be rotated and tightly protected; do not ship it to a client/plugin.

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

## Request protections

Project JSON can control request body limit, maximum concurrent requests, timeout, queue wait, gzip threshold, Trusted Host values, CORS origins, optional HTTPS enforcement and IP allow/deny CIDRs.

When saturated, rejecting quickly with `503` is safer than allowing an unbounded request queue to consume memory until the process dies.

## Rate limiting

The token-bucket limiter supports memory or Redis. Use Redis for multiple workers/servers. A key can override the project default with its own `rate_requests`, `rate_window_seconds` and `rate_burst`.

## Idempotency for money/purchases

An idempotent RPC claims `(project, operation, principal, idempotency-key)` **before** running side effects. The unique internal-DB reservation prevents two workers from executing the same transfer concurrently. A completed response is replayed on retry. A failed RPC releases its pending claim; stale pending claims can be recovered after the configured TTL.

Use stable logical IDs such as a Discord interaction ID, payment-provider event ID or order ID. Generating a different random key for every retry defeats idempotency.

## SQL safety boundary

Clients never submit raw SQL by default. Named operations contain server-owned SQL and use bind parameters. The RPC engine rejects multiple statements/comments, restricts read modes and disables DDL/administrative verbs unless explicitly allowed.

Parameter binding prevents values such as usernames or amounts from becoming SQL syntax. It does not magically make a poorly designed operation safe; permissions and domain invariants still matter.

## Secrets

Keep DB URLs, bootstrap keys, upstream tokens, JWT secrets and Redis credentials in environment variables. Never put them in mobile binaries, Discord plugins, browser JavaScript or public Git repositories.
