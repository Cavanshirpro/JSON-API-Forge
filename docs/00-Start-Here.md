# Start here: your first JSON API Forge application

This guide deliberately uses the smallest practical workflow. Advanced cache, MongoDB, realtime, media, and feature packs can wait until the basic request path is understood.

## 1. Install the project

From the repository root:

```bash
python -m venv .venv
```

Activate the environment, then:

```bash
pip install -e .
```

For contributors:

```bash
pip install -e ".[dev]"
```

## 2. Generate secrets

Do not copy a known example password into production. Run:

```bash
forge init
```

This creates a gitignored `.env` with strong random values for secret environment variables discovered in the current project configuration.

Important properties:

- `.env.example` is safe to commit because its secret values are blank;
- `forge init` refuses to overwrite an existing `.env` unless `--force` is explicitly used;
- on POSIX systems Forge attempts to set mode `0600`;
- rotating a real deployment secret is an operational action, not something CI should do automatically.

## 3. Validate before startup

```bash
forge validate
forge doctor
```

`validate` checks parsing, typing and semantic validity. `doctor` reports architecture/deployment diagnostics such as duplicate routes, unknown database aliases or dependencies.

Before production:

```bash
forge init --production
forge validate
forge doctor --production
forge migrate
```

Then configure the internal/application support-schema modes as `validate` where appropriate and restart the serving runtime. Production diagnostics intentionally reject missing/weak secrets and surface risky deployment choices such as wildcard hosts/CORS, local-only distributed primitives, runtime DDL and local media.

## 4. Run the included projects

```bash
forge dev
```

The default address is `127.0.0.1:8000`.

System endpoints:

```text
GET /health          # minimal liveness
GET /ready           # redacted readiness by default
GET /metrics         # process-wide; operator-token protected when enabled
```

Global FastAPI `/docs`, `/redoc` and `/openapi.json` are intentionally disabled. Documentation is project-scoped so one app does not accidentally publish the combined multi-project route graph.

Project-specific documentation:

```text
/api/app1/v1/_docs
/api/app1/v1/_redoc
/api/app1/v1/_openapi.json
```

## 5. Create a clean app instead of editing App1

```bash
forge new MyApi --slug my-api --preset postgres-api
forge init --force   # only if you intentionally want to regenerate the local .env
forge validate
```

The generated project looks like:

```text
app/MyApi/
├── app.json
├── config/
│   ├── 10-databases.json
│   ├── 20-security.json
│   ├── 30-performance.json
│   └── 40-resources.json
├── data/
└── hooks/
```

## 6. Understand one resource

A resource declares a server-controlled table API:

```json
{
  "resources": [
    {
      "database": "primary",
      "table": "items",
      "path": "items",
      "auto_create": true,
      "columns": {
        "id": {"type": "integer", "primary_key": true, "nullable": false},
        "name": {"type": "string", "nullable": false, "max_length": 120}
      },
      "writable_fields": ["name"],
      "allowed_sort": ["id", "name"],
      "permissions": {
        "list": "items.list",
        "read": "items.read",
        "create": "items.create",
        "update": "items.update",
        "delete": "items.delete"
      }
    }
  ]
}
```

Forge generates HTTP routes. The client talks to Forge; it does not need direct database credentials.

## 7. Create a persistent API key

The bootstrap key exists to bootstrap administration, not to become a permanent universal application secret.

Use the bootstrap value from `.env` as `X-API-Key` and call the project admin API to create a narrower key. With `bootstrap_one_time: true`, the first durable key creation and bootstrap consumption commit atomically in the internal database. The bootstrap principal is intentionally narrow: it exists to establish the first credential, not to act as a permanent `*` application administrator.

A service-specific key should have only the permissions required by that service. For example a Discord read-only plugin should not receive `*`.

## 8. Make a request

Conceptually:

```bash
curl -H "X-API-Key: $MY_API_KEY" \
  http://127.0.0.1:8000/api/my-api/v1/items
```

Create:

```bash
curl -X POST \
  -H "X-API-Key: $MY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"first"}' \
  http://127.0.0.1:8000/api/my-api/v1/items
```

## 9. When should you use a hook?

Use JSON for infrastructure-like behavior:

- a resource;
- permissions;
- database selection;
- filters/sort/pagination;
- a bounded SQL/RPC operation;
- validation;
- cache/rate policies;
- event/media declarations.

Use a trusted Python hook when the rule becomes domain logic that is hard to express declaratively, for example:

- anti-cheat validation;
- a complex entitlement decision;
- calling several domain services with compensation logic;
- a custom algorithm;
- cryptographic application logic.

Do not force every algorithm into JSON merely because Forge can define endpoints declaratively.

## 10. What to read next

If your next goal is:

- **Discord bot/database:** `08-Discord-Economy-and-PostgreSQL.md`;
- **SQL/RPC:** `09-RPC-and-SQL-Operations.md`;
- **JSON files as API:** `10-Data-Sources-and-API-Gateway.md`;
- **security:** `25-Security-Threat-Model.md`;
- **production:** `14-Operations-and-Production-Checklist.md`;
- **database migrations:** `30-Database-Schema-Lifecycle-and-Migrations.md`;
- **reverse proxy/TLS:** `31-Reverse-Proxy-Trust-TLS-and-Client-IP.md`;
- **credential delegation:** `35-Credential-Delegation-JWT-and-Operator-Trust.md`;
- **known limits:** `41-Known-Limits-and-Non-Goals.md`;
- **IDE autocomplete:** `24-JSON-Schema-and-IDE-Setup.md`.
