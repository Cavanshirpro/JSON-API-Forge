# JSON API Forge v0.1.0

**Creator / current project owner:** Cavanşir Qurbanzadə ([@Cavanshirpro](https://github.com/Cavanshirpro))  
**Canonical repository:** https://github.com/Cavanshirpro/JSON-API-Forge  
**License:** JSON API Forge Source-Available Self-Host License 1.1 — source-available, not OSI open source.


![Version](https://img.shields.io/badge/version-0.1.0-blue) ![License](https://img.shields.io/badge/license-source--available-orange) ![FastAPI](https://img.shields.io/badge/runtime-FastAPI-009688)

> **Historical release.** Initial configuration-driven FastAPI backend foundation.

JSON API Forge is a configuration-driven backend runtime built around FastAPI. Its long-term goal is to move reusable backend infrastructure—database routing, API policies, authentication, authorization, caching, limits, resource definitions and integration behavior—into application configuration under `app/`, while reserving Python hooks for logic that genuinely needs code.

## License at a glance

JSON API Forge is **source-available, not OSI open source**. You may inspect the source, self-host official releases, use them commercially, and privately modify them for your own deployment. You may **not redistribute** the framework or publish an alternative modified/unmodified distribution, package, image or maintained fork, except for the narrow contribution-fork workflow described in `LICENSE`.

See [`LICENSE`](LICENSE), [`LICENSE-FAQ.md`](LICENSE-FAQ.md), [`NOTICE.md`](NOTICE.md), [`OWNERSHIP.md`](OWNERSHIP.md), [`AUTHORS.md`](AUTHORS.md), and [`GOVERNANCE.md`](GOVERNANCE.md).

## Release information

- Version: **0.1.0**
- Release notes: [`RELEASE.md`](RELEASE.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Publishing all three historical releases: [`GITHUB_PUBLISHING.md`](GITHUB_PUBLISHING.md)
- Release asset guidance: [`RELEASE_ASSETS.md`](RELEASE_ASSETS.md)
- Ownership and future company transfer: [`OWNERSHIP.md`](OWNERSHIP.md)

---

**JSON API Forge** is a configuration-driven FastAPI backend foundation. Its goal is to make a new backend mostly a matter of editing JSON files instead of rewriting authentication, authorization, CRUD, database routing, API-key handling, pagination and deployment glue for every application.

> This repository is a strong extensible foundation, not a claim that arbitrary business logic can always be represented safely in JSON. Complex domain rules belong in small Python hook functions, while infrastructure and common CRUD policy stay declarative.

## What you get

- FastAPI + automatic OpenAPI/Swagger documentation
- PostgreSQL/Supabase, MySQL/MariaDB and SQLite through async SQLAlchemy
- Multiple databases in one application, selected per resource
- Existing-table reflection or JSON-declared table creation
- API keys stored only as SHA-256 hashes in the internal database
- Bootstrap admin key sourced from environment variables
- RBAC roles, role inheritance, direct permissions and wildcard permissions
- Per-resource/action permissions
- Optional JWT bearer authentication foundation
- Configurable CRUD, readable/writable fields, filtering, sorting and pagination
- Optional tenant column enforcement for multi-tenant resources
- Optional soft-delete column
- Request IDs, basic security headers, structured-ish access logging
- CORS configuration
- In-memory rate limiting; designed so Redis can replace it for multi-process production
- Custom Python hooks registered from JSON for business logic and plugin APIs
- cPanel/Passenger entrypoint via ASGI-to-WSGI bridge
- Config validation and secret-generation scripts
- Tests and detailed documentation

## 1. Quick start

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\\Scripts\\Activate.ps1

pip install -r requirements.txt
cp .env.example .env
python scripts/generate_secret.py
python scripts/validate_config.py
python run.py
```

Open:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

The sample project automatically creates a SQLite `notes` table.

## 2. Create the first API key

Put a strong value in `.env`:

```env
BOOTSTRAP_ADMIN_KEY=your-long-random-secret
```

Then create an ordinary API key. The bootstrap key is intentionally only a root/bootstrap credential.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/api-keys \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-long-random-secret' \
  -d '{"name":"my-plugin","roles":["plugin"],"permissions":[]}'
```

The returned `api_key` is shown **once**. Store it securely. The server stores only its hash.

## 3. Define an API resource using JSON

```json
{
  "database": "primary",
  "table": "notes",
  "path": "notes",
  "auto_create": true,
  "primary_key": "id",
  "columns": {
    "id": {"type": "integer", "primary_key": true, "nullable": false},
    "title": {"type": "string", "nullable": false},
    "content": {"type": "text"}
  },
  "permissions": {
    "list": "notes.list",
    "read": "notes.read",
    "create": "notes.create",
    "update": "notes.update",
    "delete": "notes.delete"
  },
  "writable_fields": ["title", "content"],
  "allowed_filters": ["title"],
  "allowed_sort": ["id", "title"]
}
```

This produces common REST routes under `/api/v1/notes`.

## 4. Use Supabase/PostgreSQL

Set the async SQLAlchemy URL in `.env`:

```env
PRIMARY_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
```

Supabase is PostgreSQL, so use the connection information supplied by your Supabase project/pooler and express it as a `postgresql+asyncpg://...` URL.

For MySQL:

```env
MYSQL_DATABASE_URL=mysql+asyncmy://USER:PASSWORD@HOST:3306/DATABASE
```

Then add that environment variable to `databases` in `app/config/app.json` and select its alias on any resource.

## 5. Plugin/business endpoints

CRUD is declarative. Complex logic stays in a hook:

```json
{
  "path": "plugin/ping",
  "method": "POST",
  "permission": "custom.ping",
  "handler": "app.hooks.example:ping_plugin"
}
```

A plugin can receive its own API key and only the permissions it needs. Never distribute the bootstrap admin key to plugins.

## Repository map

```text
json_api_forge/
├── main.py                  # normal ASGI entrypoint
├── run.py                   # Uvicorn development/server runner
├── passenger_wsgi.py        # cPanel Passenger bridge
├── requirements.txt
├── .env.example
├── framework/               # reusable engine
│   ├── config.py
│   ├── crud.py
│   ├── db.py
│   ├── factory.py
│   ├── hooks.py
│   ├── rate_limit.py
│   ├── security.py
│   └── settings.py
├── app/
│   ├── config/app.json      # most app-specific work happens here
│   └── hooks/               # only when JSON is not enough
├── scripts/
├── tests/
└── docs/
```

## Important production rules

1. Do not put real passwords/API keys into committed JSON. Use `$env:VARIABLE`.
2. Rotate the bootstrap key after initial provisioning and do not give it to plugins.
3. Use PostgreSQL/MySQL for production; SQLite is mainly for development and small single-process installs.
4. On multi-worker/multi-server deployments, use a shared rate-limit/cache backend rather than process memory.
5. Put TLS/HTTPS in front of the API.
6. Set exact CORS origins in production instead of `"*"`.
7. Add application-specific validation/hook logic before exposing sensitive tables.
8. Use a real migration workflow (Alembic) for long-lived production schemas; `auto_create` is intentionally simple.

See `docs/` for the full design and `docs/cPanelGuide.md` for cPanel deployment.

## Repository policy

Only Cavanşir Qurbanzadə (@Cavanshirpro), or a lawful successor/assignee, may designate Official Releases or authorize alternative distribution. External contributions are welcome through the canonical repository subject to the CLA and project governance. Do not commit `.env`, credentials, database files, private keys, production logs or sensitive user data.