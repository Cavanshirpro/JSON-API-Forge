# Architecture

## Design goal

The framework separates **infrastructure policy** from **application logic**.

- `framework/` should rarely change between projects.
- `app/config/app.json` describes databases, resources, roles and endpoints.
- `app/hooks/` contains the small amount of code required for rules that should not be expressed as generic JSON.
- `.env` contains secrets and environment-specific connection strings.

This is intentionally similar to a tiny domain-specific backend language: JSON describes *what* should be exposed, and the framework decides *how* to expose it safely.

## Request path

1. FastAPI receives the request.
2. Request middleware assigns/preserves `X-Request-ID`.
3. Authentication checks, in order: bootstrap key, persistent API key, JWT, anonymous.
4. Rate limiter evaluates the resolved principal and route.
5. The route checks its required permission.
6. A configured resource chooses a database alias and SQLAlchemy Table.
7. CRUD policy applies writable/readable fields, tenant constraints, filters, sorting and limits.
8. The async database engine executes the statement.
9. The response is serialized with ORJSON.

## Why SQLAlchemy Core rather than ORM models for every table?

A config-driven system cannot reasonably require a handwritten Python ORM class for every JSON-defined table. SQLAlchemy Core supports reflected existing tables and dynamically declared tables without generating Python source code.

## Internal database

The framework uses `INTERNAL_DATABASE_URL` for its own security metadata, currently API-key records. Keeping internal framework data separate allows the application data database to be changed or hosted externally.

For production, point it at PostgreSQL as well if you run multiple instances.

## What belongs in JSON vs Python hooks?

Good JSON candidates:

- database aliases
- table-to-route mappings
- CRUD exposure
- permissions
- field allowlists
- filters/sorting/pagination limits
- tenant column
- soft-delete column
- rate-limit policy
- custom endpoint path/method/permission/handler mapping

Use Python hooks for:

- transactions spanning multiple tables
- payment logic
- complex validation
- external API orchestration
- cryptography beyond standardized framework services
- file/image processing
- domain state machines
- operations where ordering/locking/idempotency matter

Trying to encode arbitrary business logic into JSON eventually creates a worse programming language. Hooks are the escape hatch that keeps the system maintainable.
