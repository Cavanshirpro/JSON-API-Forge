# Configuration reference

The primary file is `app/config/app.json`.

## Environment interpolation

Any complete JSON string in this format is replaced at startup:

```json
"$env:VARIABLE"
```

A default is supported:

```json
"$env:VARIABLE:-fallback-value"
```

Use it for connection strings and secrets. Do not commit real production secrets.

## Top-level fields

### `name`, `version`
Metadata shown in OpenAPI.

### `api_prefix`
Base path for generated routes, e.g. `/api/v1`.

### `docs_enabled`
Controls FastAPI Swagger/ReDoc routes.

### `cors_origins`
Allowed browser origins. Use explicit domains in production.

### `databases`
Map from an arbitrary alias to a SQLAlchemy async URL.

```json
"databases": {
  "primary": {"url": "$env:PRIMARY_DATABASE_URL"},
  "mysql": {"url": "$env:MYSQL_DATABASE_URL"}
}
```

Supported by included drivers:

- PostgreSQL / Supabase: `postgresql+asyncpg://...`
- MySQL/MariaDB: `mysql+asyncmy://...`
- SQLite: `sqlite+aiosqlite:///...`

### `security`

- `api_key_header`: normally `X-API-Key`
- `bootstrap_admin_key`: use `$env:BOOTSTRAP_ADMIN_KEY`
- `jwt_enabled`: enables Bearer JWT parsing
- `jwt_exp_minutes`: default token lifetime for future auth flows
- `allow_query_api_key`: disabled by default because URLs leak into logs/history more easily

### `roles`
Roles can contain permissions and inherit other roles.

```json
"roles": {
  "reader": {"permissions": ["notes.list", "notes.read"]},
  "editor": {
    "inherits": ["reader"],
    "permissions": ["notes.create", "notes.update"]
  }
}
```

Wildcard rules:

- `*` grants everything.
- `notes.*` matches `notes.list`, `notes.read`, etc.

### `resources`
Each resource maps a table to REST endpoints.

Important fields:

- `database`: database alias
- `table`: physical table name
- `path`: URL segment
- `enabled`: include/exclude without deleting config
- `auto_create`: create a simple table from `columns`
- `columns`: only necessary for `auto_create`
- `primary_key`: route lookup key
- `allowed_actions`: subset of `list`, `read`, `create`, `update`, `delete`
- `permissions`: override action permission strings
- `readable_fields`: response allowlist
- `writable_fields`: request-body allowlist
- `hidden_fields`: always removed from response
- `default_limit`, `max_limit`: pagination bounds
- `allowed_filters`: exact-match query filters
- `allowed_sort`: accepted `sort=field` and `sort=-field`
- `soft_delete_field`: if set, DELETE writes a timestamp instead of deleting
- `tenant_field`: automatically constrains rows to JWT `tenant_id`

### `custom_endpoints`
Maps a URL to a Python callable:

```json
{
  "path": "billing/recalculate",
  "method": "POST",
  "permission": "billing.recalculate",
  "handler": "app.hooks.billing:recalculate",
  "summary": "Recalculate account billing"
}
```

Handlers receive keyword arguments `request`, `payload`, `principal`, and `app`.
