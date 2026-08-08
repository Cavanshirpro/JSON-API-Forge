# Credential Delegation, JWT, and Operator Trust

Credential issuance is an authorization action, not an ordinary CRUD operation. A principal that can create a credential must not automatically be able to create a credential stronger than itself.

## 1. Credential classes

Forge separates:

- bootstrap credential — narrow one-time setup capability;
- persistent API keys — integration/client credentials;
- local JWTs — short-lived delegated application credentials;
- external JWKS JWTs — credentials issued by an external identity provider;
- operator token — process-wide operational telemetry credential.

## 2. Bootstrap is not `*`

Bootstrap exists to establish the first durable administrator credential. It is intentionally not a permanent omnipotent principal for application resources or arbitrary JWT minting.

The first durable API-key insert and one-time bootstrap consumption occur in the same internal-database transaction, preventing two racing first-admin requests from both committing.

## 3. Delegation containment

A delegated credential is constrained by the issuer unless the issuer has explicit high-trust delegation authority.

Containment checks include relevant dimensions such as:

- permissions;
- roles;
- tenant;
- expiry;
- traffic budgets;
- JWT subject/impersonation.

This prevents a principal with only `admin.keys.create`/`admin.jwt.issue` from silently minting `*`, changing tenant, creating a non-expiring child from an expiring parent, or impersonating an arbitrary owner.

The same containment principle is applied when revoking a key: a delegated administrator without `admin.credentials.delegate_any` cannot use a narrow revocation capability to disable a credential that it would not be allowed to delegate/create. This avoids a delegated-admin denial-of-service path against stronger/root credentials.

## 4. API-key metadata cache

Successful API-key metadata lookups can use a small bounded process-local cache:

```json
{
  "security": {
    "api_key_cache_ttl_seconds": 2,
    "api_key_cache_max_entries": 10000
  }
}
```

The database remains authoritative.

### Revocation semantics

- create/revoke invalidates the cache in the worker performing the action;
- another worker may retain a previously successful cached key until its short TTL expires;
- set TTL to `0` when immediate per-request database authority is more important than auth lookup throughput;
- production doctor warns on unusually long revocation windows.

This is not a distributed revocation bus.

## 5. Local JWT

JWT is disabled by default. Local HS256 should use a project-scoped secret:

```json
{
  "security": {
    "jwt_enabled": true,
    "jwt_provider": "local_hs256",
    "jwt_secret": "$env:APP1_JWT_SECRET"
  }
}
```

A global `JWT_SECRET` fallback exists for compatibility but weakens project isolation and is surfaced by production diagnostics.

## 6. External JWKS JWT

For external verification:

```json
{
  "jwt_enabled": true,
  "jwt_provider": "jwks",
  "jwt_jwks_url": "$env:IDP_JWKS_URL",
  "jwt_issuer": "$env:IDP_ISSUER",
  "jwt_audience": "my-api",
  "jwt_require_project_claim": true
}
```

JWKS verification accepts only configured asymmetric signing algorithms. Key metadata is checked before use.

## 7. External authorization claims are not trusted automatically

Identity verification and authorization are different. External `roles`, `permissions` and `tenant_id` claims are opt-in trust decisions:

```json
{
  "jwt_trust_roles_claim": false,
  "jwt_trust_permissions_claim": false,
  "jwt_trust_tenant_claim": false
}
```

If external authorization/tenant claims are trusted, project binding should normally remain required.

## 8. Operator token

`/metrics` and detailed process-wide readiness describe more than one project. App1 administrator credentials therefore do not automatically grant operator telemetry access for App2.

Use a separate strong `OPERATOR_TOKEN`.

## 9. Secret rotation

`forge init --force` rotates Forge-managed secret assignments while preserving user-owned `.env` lines. Rotation still requires operational planning:

- API keys should normally be replaced using key lifecycle endpoints;
- rotating JWT secrets invalidates tokens signed with the old key unless overlap/key rotation is designed externally;
- media signing secrets affect outstanding signed URLs;
- operator-token rotation must be coordinated with monitoring.
