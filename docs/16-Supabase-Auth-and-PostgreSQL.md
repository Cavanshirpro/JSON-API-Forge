# Supabase Auth + PostgreSQL

Forge can use Supabase in two separate ways:

1. **Database:** Supabase PostgreSQL is configured as an ordinary async PostgreSQL database alias (`postgresql+asyncpg://...`). Database credentials stay on the Forge server.
2. **Authentication:** a web/mobile client can send its Supabase bearer JWT to Forge. Forge can validate an asymmetric JWT from a configured JWKS endpoint and map JWT claims into Forge roles, permissions and `tenant_id`.

## Recommended split

```text
Web/mobile client
  ├─ signs in with Supabase Auth
  └─ sends Authorization: Bearer <access token>
                ↓
            Forge API
  ├─ validates signature/issuer/audience
  ├─ maps app_metadata roles/permissions
  └─ talks to PostgreSQL using server credentials

Discord bot / trusted plugin
  └─ X-API-Key: narrow Forge key
                ↓
            Forge API
```

A public client never needs the PostgreSQL password or a privileged server key.

## JSON configuration

See `examples/supabase_auth/security-fragment.json`.

Typical environment variables:

```env
SUPABASE_JWKS_URL=https://YOUR_PROJECT.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_JWT_ISSUER=https://YOUR_PROJECT.supabase.co/auth/v1
APP1_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/postgres
```

Example claim mapping:

```json
{
  "security": {
    "jwt_provider": "jwks",
    "jwt_roles_claim": "app_metadata.roles",
    "jwt_permissions_claim": "app_metadata.permissions",
    "jwt_tenant_claim": "app_metadata.tenant_id"
  }
}
```

Dotted claim paths are supported. A string claim becomes one role/permission; arrays become sets.

## JWKS cache and key rotation

Signing keys are cached for `jwks_cache_ttl_seconds` so every request does not call Supabase. If a JWT references an unknown `kid`, Forge forces one JWKS refresh before rejecting it, which helps during signing-key rotation.

The configured algorithm allow-list, issuer and audience are checked. Do not disable these checks merely to make a malformed token work.

## Local Forge JWT vs external JWKS

`jwt_provider:"local_hs256"` keeps Forge's built-in `/admin/jwt` issuer.

`jwt_provider:"jwks"` treats another identity provider such as Supabase as the issuer. Forge does **not** expose its local JWT-issuing endpoint in that mode, preventing two unrelated issuer models from being mixed accidentally.
