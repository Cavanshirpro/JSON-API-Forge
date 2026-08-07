# Security model

## Bootstrap admin key

The bootstrap key is intentionally powerful. It exists so a fresh installation can create its first normal API keys. Keep it in `.env`, not in a committed JSON file.

Recommended lifecycle:

1. Generate a long random key.
2. Start the server.
3. Use it to create an administrator API key.
4. Replace/rotate the bootstrap key and keep it offline if practical.
5. Never ship it inside desktop/mobile apps or plugins.

## API keys

Generated keys begin with `jf_`. The full key is returned only on creation. The internal database stores a SHA-256 hash plus metadata, roles and direct permissions.

A leaked database therefore does not directly reveal active plaintext API keys. However, treat the database as sensitive because authorization metadata remains valuable.

## Plugin model

Every plugin should get a separate key. This enables:

- least privilege
- independent revocation
- future per-key quotas
- future per-key audit attribution

Example: a read-only analytics plugin needs `orders.list` and `orders.read`, not `*`.

## RBAC + permissions

Roles are convenience bundles. Enforcement ultimately uses permission strings. You can give a key both roles and direct permissions.

## JWT

The core can authenticate HS256 bearer JWTs using `JWT_SECRET`. A complete user login/password/OAuth flow is application-specific and should be added as hooks or a dedicated auth module. Do not create a fake one-size-fits-all user schema if your applications may use Supabase Auth, Google OAuth, Discord OAuth or custom identity providers.

## Tenant isolation

For resources with `tenant_field`, JWT callers must contain `tenant_id`; CRUD statements are automatically constrained to that tenant.

API keys currently do not carry a tenant ID in the stored schema. If you use API keys for tenant-specific clients, extend the key metadata with tenant binding before production use.

## Production checklist

- HTTPS only
- exact CORS allowlist
- strong `.env` secrets
- database user with minimum SQL privileges
- no query-string API keys
- restrict `/docs` for private production APIs if desired
- put rate limits at both app and reverse-proxy/WAF levels
- monitor 401/403/429 spikes
- keep dependencies updated
- use database backups
- use migrations for schema evolution
- add audit retention policy if handling important actions
