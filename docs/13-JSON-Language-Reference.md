# JSON language reference

This file is a map of the current v0.4 declarative surface. Exact field types/defaults are also available from `schemas/project.schema.json` and `schemas/fragment.schema.json`.

## Top-level project keys

```text
slug, name, version, enabled, api_prefix
docs_enabled, audit_enabled, cors_origins
databases, mongo_databases
security, cache, rate_limit, protection, observability, realtime
roles
resources, mongo_resources
operations
data_sources
dependencies, custom_endpoints
event_channels, webhook_docs
media
features
```

## `databases`

Named async SQLAlchemy databases. Important fields:

```text
url
echo
pool_pre_ping
pool_size
max_overflow
pool_timeout
pool_recycle
isolation_level
```

Supported in this distribution through installed async drivers: PostgreSQL (`asyncpg`), MySQL/MariaDB (`asyncmy`) and SQLite (`aiosqlite`). Supabase database access uses PostgreSQL.

## `mongo_databases`

Named MongoDB connections:

```text
uri, database, max_pool_size, min_pool_size, server_selection_timeout_ms
```

## `security`

```text
api_key_header
bootstrap_enabled, bootstrap_admin_key, bootstrap_one_time
jwt_enabled                       # default: false in v0.4
jwt_provider: local_hs256 | jwks
jwt_secret                        # project-scoped local HS256 secret; prefer $env:...
jwt_exp_minutes
jwt_jwks_url, jwt_issuer, jwt_audience, jwt_algorithms
jwt_subject_claim, jwt_roles_claim, jwt_permissions_claim
jwt_tenant_claim, jwt_project_claim
jwks_cache_ttl_seconds, jwks_timeout_seconds
allow_query_api_key, allow_websocket_query_api_key
require_https, allowed_ips, denied_ips
idempotency_header
```

## `cache`

```text
enabled
backend: memory | redis | tiered
default_ttl_seconds, stale_ttl_seconds
max_entries, key_prefix
cache_lists, cache_reads
fail_open
```

Resource cache can override enable/TTL values, including `stale_ttl_seconds` (set `0` for strongly-consistent reads such as balances).

## `rate_limit`

```text
enabled
requests, window_seconds, burst          # principal-global primary budget
route_requests, route_window_seconds, route_burst
backend: memory | redis
memory_max_buckets
memory_idle_ttl_seconds
memory_cleanup_interval_seconds
fail_open
```

API keys can have their own request/window/burst settings.

## `protection`

```text
max_request_body_bytes
max_concurrent_requests
request_timeout_seconds
trusted_hosts
gzip_minimum_size
reject_when_saturated
max_queue_wait_seconds
```

## `resources`

Relational table mapping:

```text
database, table, path, enabled, auto_create
columns, primary_key
allowed_actions, permissions
readable_fields, writable_fields, hidden_fields
allowed_filters, filter_operators, search_fields, allowed_sort
pagination_mode, cursor_field
tenant_field, soft_delete_field
cache
create_schema, update_schema
batch_enabled, max_batch_size, count_enabled
dependencies
```

Filter query syntax:

```text
?balance__gte=100
?id__in=1,2,3
?q=search text
?sort=-created_at
```

## `mongo_resources`

Similar CRUD policy for a Mongo collection: database alias, collection/path, actions/permissions, write/hidden fields, filter operators, sort, tenant/soft-delete, cache and JSON Schemas.

## `operations`

Named server-owned SQL/RPC:

```text
name, path, method, database
public, permission
transaction
input_schema, parameters
statements[]
allow_ddl
idempotency
cache
invalidate_resources, invalidate_operations
summary, description, tags, deprecated
dependencies, background_hooks
```

Statement:

```text
sql
mode: execute | fetch_one | fetch_all | scalar
params
result_name
max_rows
require_rowcount_min / max
```

## `data_sources`

```text
name, enabled, path
type: json_file | yaml_file | csv_file | static | http
public, public_write
permission / read_permission / write_permission
parameters
file / data / url
method, headers, timeout_seconds, retries
retry_non_idempotent              # default false; POST/PATCH retries require explicit opt-in
writable, id_field, max_items
cache_ttl_seconds, stale_ttl_seconds
file_lock_timeout_seconds
forward_query, forward_body
dependencies
```

## `dependencies`

Trusted FastAPI dependency imports:

```json
{"name":"x","callable":"module:function","use_cache":true}
```

## `custom_endpoints`

```text
path, method, public, permission, handler
summary, description, tags, deprecated, include_in_schema
input_schema
input_mode: json | form | text | bytes | none
parameters, dependencies, background_hooks
response
openapi_extra
```

Response kinds: `json`, `text`, `html`, `redirect`, `stream`, `file`, `empty`.

## `event_channels`

```text
name, path
public_publish, public_subscribe
publish_permission, subscribe_permission
websocket_enabled, sse_enabled
max_message_bytes, queue_size, heartbeat_seconds
websocket_message_requests, websocket_message_window_seconds, websocket_message_burst
```

Use `realtime.backend:"redis"` for cross-worker delivery.

## `media`

```text
enabled
backend: local
local_directory
max_upload_bytes, max_batch_files, max_owner_bytes
allowed_mime_types, allowed_extensions
public
upload/read/delete/admin permissions
owner_delete_only
deduplicate, deduplicate_scope: owner | project
signed_urls_enabled, signed_url_ttl_seconds
post_upload_hooks
```

v0.4 exposes only the implemented `local` backend. Future object-storage adapters will become valid configuration only when an implementation and tests exist. `deduplicate_scope` defaults to `owner` so a duplicate upload does not reveal another principal's existing metadata. API metadata responses deliberately omit the internal `storage_key`; owner identity is only included for the owner or a caller with `media.admin`.

## `features`

Feature packs currently generate baseline relational resources for:

```text
messaging
social
gaming
```

They accelerate common schemas but do not replace domain authorization/business rules.

## Environment references

```text
$env:NAME
$env:NAME:-fallback
```

are resolved after fragments merge and before validation.

## Extension ABI

Python references use:

```text
package.module:function
```

Only server owners should control these values.


## v0.4 strictness rules

All configuration objects reject unknown properties. For private-capable endpoint types, omission is not treated as anonymous access: define a permission or an explicit public flag. Generated schemas are authoritative for exact types/defaults and should be refreshed with `forge schema`. Cross-field/merged-project rules are additionally checked by `forge validate` and `forge doctor`.

## v0.4 security-sensitive defaults

Several defaults are intentionally conservative:

- `security.jwt_enabled` defaults to `false`; enable JWT only when the project has an issuer contract.
- for `local_hs256`, prefer `security.jwt_secret: "$env:APP_NAME_JWT_SECRET"`; a global `JWT_SECRET` remains a compatibility fallback and `forge doctor --production` warns about shared-secret isolation;
- operations, custom endpoints and data-source reads are private unless they declare a permission or explicit `public:true`;
- writable data sources require a write permission or explicit `public_write:true`;
- event publish/subscribe directions each require a permission or their own explicit public flag;
- automatic retries for `POST`/`PATCH` HTTP data sources are disabled unless `retry_non_idempotent:true` is explicitly configured.

These defaults are part of the runtime contract, not merely documentation conventions.
