# Recipes and decision guide

## I have a PostgreSQL table and want CRUD

Use `resources[]`.

```json
{
  "resources":[{
    "database":"primary",
    "table":"users",
    "path":"users",
    "allowed_actions":["list","read","create","update"],
    "allowed_filters":["username","level"],
    "filter_operators":["eq","gte","lte"],
    "writable_fields":["username","level"]
  }]
}
```

Forge reflects the existing table when `auto_create:false`.

## I need a multi-table/transaction command

Use `operations[]` rather than several client CRUD requests. Examples: transfer money, purchase item, claim reward, move inventory, accept friend request with side effects.

## I need complex Python logic

Use a `custom_endpoint` hook. Keep auth/permission/input schema in JSON and put only exceptional business code in Python.

## I have JSON/YAML content

Use `data_sources`. Make it read-only for configuration/content; enable writable only for small datasets where file locking and atomic replacement are sufficient.

## I need to hide a third-party API key

Use an `http` data source. Client → Forge → upstream. Put the upstream token in environment-referenced headers.

## I have document-shaped data

Use `mongo_databases` + `mongo_resources`. Use PostgreSQL when relational transactions/constraints dominate; MongoDB when document flexibility is the better fit.

## I need Supabase

Use Supabase PostgreSQL as a SQL database alias. Optionally set `jwt_provider:"jwks"` to validate Supabase Auth bearer tokens. See `16-Supabase-Auth-and-PostgreSQL.md`.

## I need a Discord/Minecraft/game server plugin

Create a separate API key for that plugin. Let the plugin call Forge via HTTP. Do not distribute DB credentials. Put transactional logic in named RPCs.

## I need browser/mobile users

Use JWT user identity and CORS. Do not embed a privileged Forge API key or PostgreSQL password into the application package.

## I need notifications/feed updates

Use `event_channels` with SSE for one-way streaming or WebSocket for duplex messages. Use Redis realtime backend with multiple workers.

## I need media

Enable `media` for upload/download metadata, size/MIME/extension policy, dedupe, owner quota and signed temporary URLs. Use trusted post-upload hooks to schedule lightweight follow-up; heavy processing belongs in a worker queue.

## I need huge list pages

Use cursor/keyset pagination on SQL resources, allowed indexed sort/filter fields and cache hot reads. Avoid enormous offsets and unbounded result sets.

## I need arbitrary SQL from an admin tool

Prefer defining a narrow named admin operation for each task. A generic remote SQL console is intentionally not generated because one leaked admin key would become a full database execution primitive.

## I need a FastAPI feature not represented in JSON

First check `11-FastAPI-Declarative-Features.md`. If the behavior is code by nature, implement a trusted dependency/hook and reference it from JSON. The framework deliberately keeps a code extension boundary instead of turning configuration into arbitrary code execution.
