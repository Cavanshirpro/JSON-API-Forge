# Upgrading from 0.2

0.3 is intentionally a larger architectural release. Treat the change as an application upgrade, not merely replacing one Python file.

## Preserve first

Back up your app folders, `.env`, database schemas/data, API key/internal metadata database and uploaded media.

## App folders

The `app/App1/...`, `app/App2/...` layout is preserved. Existing relational resources/security/cache configuration remains conceptually compatible, but validate every app with the v0.3 schema because new validation is stricter in several places.

## New capabilities

0.3 adds named SQL RPC operations, data sources, Mongo resources, declarative request parameters/dependencies/responses, SSE/WebSocket channels, JWKS JWT validation, stronger media policy, cross-worker idempotency claims and more detailed cache controls.

## Internal metadata database

The sample `.env` uses `internal-v3.db`. If you intentionally reuse an old internal DB, migrate its Forge internal tables rather than assuming `create_all()` will alter existing columns. SQLAlchemy `create_all()` creates missing tables; it is not a schema migration engine.

For production upgrades, use a dedicated shared PostgreSQL internal database and explicit migration/backup procedure.

## Test route contracts

Run:

```bash
python forge.py validate
python forge.py routes
pytest -q
```

Then compare your client-used endpoints with `<prefix>/_openapi.json` before switching traffic.
