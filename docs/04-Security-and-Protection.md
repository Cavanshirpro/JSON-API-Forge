# Security and protection

Implemented protections include project-scoped API keys, SHA-256 key hashes, RBAC inheritance, wildcard permissions, JWT project binding, optional tenant IDs, IP allow/deny CIDRs, optional HTTPS enforcement, request body limits, concurrency backpressure, request timeouts, per-project CORS, Trusted Host filtering, security headers and rate limiting.

## API keys

Bootstrap keys exist only for provisioning. Plugins and applications should receive separate keys with least privilege. Rotation is done by creating a replacement, deploying it, then revoking the old key.

## Permissions

Feature packs use dotted permissions such as:

```text
messaging.messages.create
social.posts.read
gaming.leaderboard.list
```

`social.*` therefore covers all generated social permissions.

## Multi-tenant data

Set `tenant_field` on a resource and ensure JWT principals contain a `tenant_id`. Forge then adds the tenant condition to list/read/update/delete and inserts the tenant ID on create.

## What JSON must not bypass

Generic CRUD cannot by itself enforce domain invariants such as membership, ownership, anti-cheat verification, moderation policy, balance transfers or purchase settlement. Put these in hooks/services and expose only the safe endpoint to untrusted clients.

## Deployment

Terminate TLS at the reverse proxy. Never expose database ports publicly. Prefer Redis authentication/private networking. Use exact Trusted Host and CORS values in production.

## Per-key traffic budgets

When creating an API key, administrators may assign `rate_requests`, `rate_window_seconds` and `rate_burst`. A key may also be bound to a `tenant_id`. This is useful when official clients, internal services and third-party plugins need different limits despite sharing parts of the same permission model.
