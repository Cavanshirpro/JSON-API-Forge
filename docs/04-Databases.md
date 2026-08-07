# Databases

## PostgreSQL

Recommended production backend. Use `asyncpg` through SQLAlchemy:

```env
PRIMARY_DATABASE_URL=postgresql+asyncpg://user:password@host:5432/db
```

## Supabase

Supabase databases are PostgreSQL. Put the project/pooler connection information into the same PostgreSQL async URL form. Authentication provided by Supabase Auth is a separate concern from database connectivity; integrate its JWT verification as a dedicated identity adapter when you choose that model.

## MySQL / MariaDB

```env
MYSQL_DATABASE_URL=mysql+asyncmy://user:password@host:3306/db
```

Then register the alias in JSON.

## Multiple databases

A single app may define:

```json
"databases": {
  "core": {"url": "$env:CORE_DB"},
  "analytics": {"url": "$env:ANALYTICS_DB"},
  "legacy": {"url": "$env:LEGACY_MYSQL_DB"}
}
```

Each resource chooses one alias. This is useful for plugins, legacy databases, analytics stores and staged migrations.

## Reflection vs auto-create

`auto_create: false` reflects an existing table at startup. This is suitable when schemas are managed externally/Alembic.

`auto_create: true` creates a basic table from JSON column specs. This is convenient for small projects and prototypes but is not a substitute for full migration history.

## Recommended future adapter boundary

If you later add MongoDB, DynamoDB, Elasticsearch or a REST-only upstream, do not force them through SQLAlchemy-table semantics. Add a `ResourceAdapter` interface with list/read/create/update/delete methods and select an adapter type in JSON. This keeps the declarative layer stable while allowing non-relational stores.
