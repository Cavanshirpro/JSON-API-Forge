# API Semantics and HTTP Contracts

Declarative APIs are useful only if generated endpoints have predictable semantics. v0.4 tightens behavior that was ambiguous in earlier releases.

## 1. Authentication status codes

Forge distinguishes:

- `401 Unauthorized`: authentication is required but no valid principal is available;
- `403 Forbidden`: a valid principal exists but lacks the required permission/policy.

## 2. Public is explicit

Operations, custom endpoints, data sources and event channels are private by default. Public access requires explicit configuration such as `public:true`, `public_write:true`, `public_publish:true` or `public_subscribe:true` where supported.

Omitting a permission is not a shortcut to public access.

## 3. PATCH versus PUT

### PATCH

Partial mutation. Fields not supplied remain unchanged.

### PUT

Replacement semantics for the writable application representation. Missing writable fields are treated according to replacement behavior rather than silently behaving like PATCH.

Protected fields such as tenant/owner/soft-delete metadata are still server-controlled.

SQL, Mongo and writable file-backed resources follow this distinction.

## 4. Stable pagination

Offset pagination uses a deterministic default order rather than relying on database natural order.

Cursor pagination uses a stable composite cursor so repeated values in a custom cursor field do not silently skip rows. A cursor is opaque to clients; clients should return the `next_cursor` exactly as supplied.

Invalid combinations such as offset controls in cursor mode are rejected instead of silently ignored when the strict contract applies.

## 5. Validation

Configuration is strict Pydantic input (`extra="forbid"`). Request payloads can additionally use JSON Schema/configured field rules. Validation errors should expose field/location information without echoing resolved environment secrets.

## 6. Conflict handling

Expected database integrity conflicts are mapped to controlled API responses rather than leaking raw driver exceptions. Applications should still define domain-specific conflict behavior in RPC/hooks where a generic unique-constraint response is insufficient.

## 7. Cache observability

Cache state is transport metadata, not application JSON. Generated responses use:

```text
X-Forge-Cache: hit|miss|stale|...
```

Forge does not inject a synthetic `_cache` field into user payloads.

## 8. Request IDs

`X-Request-ID` is bounded to the storage/logging contract. Forge can generate an ID when absent and propagates it in the response. Request IDs are diagnostic correlation values, not authorization credentials and not idempotency keys.

## 9. Idempotency keys

An idempotency key represents one logical mutation request. Reusing the same key with different canonical request input yields conflict rather than replaying a different request's result.

Do not use request IDs as idempotency keys: retries naturally receive different request IDs.

## 10. Response-size policies

Outbound HTTP data sources enforce a configured maximum while streaming upstream bytes. Uploads and inbound request bodies also have size policies. These are resource-protection controls, not content security scanners.

## 11. OpenAPI

Project OpenAPI reflects public/private semantics. Global FastAPI default `/docs`, `/redoc` and `/openapi.json` are disabled so one project cannot accidentally expose the combined route graph through framework defaults.

Project documentation is controlled by `docs_enabled` and should be treated as an operational exposure decision in production.

## 12. Route collisions and shadowing

`forge doctor` checks exact method/path collisions and important dynamic/static shadowing patterns. Generated routes should not depend on accidental registration order.
