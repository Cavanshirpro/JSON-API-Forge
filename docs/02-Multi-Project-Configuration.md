# Multi-project configuration

Every direct folder under `app/` that contains `app.json` or `manifest.json` becomes one API application.

```text
app/
├── DiscordEconomy/
│   ├── app.json
│   ├── config/
│   │   ├── 10-databases.json
│   │   ├── 20-security.json
│   │   ├── 30-performance.json
│   │   ├── 40-resources.json
│   │   ├── 50-features.json
│   │   ├── 70-operations.json
│   │   └── 80-integrations.json
│   ├── data/
│   └── hooks/
└── SocialApp/
    └── ...
```

## Loading and merge order

1. Read `app.json`.
2. Read every `config/*.json` in lexical/alphabetical order.
3. Deep-merge them.
4. Resolve environment references.
5. Validate the final object with Pydantic.
6. Expand feature packs.
7. Generate FastAPI routes during application construction.

Merge rules:

```text
object + object → recursive merge
array  + array  → append
scalar + scalar → later value wins
```

This means you can keep database credentials, security, resources and integrations conceptually separate while they still form one app config at runtime.

## Environment references

Any value that exactly matches one of these forms is resolved server-side:

```text
$env:VARIABLE
$env:VARIABLE:-fallback
```

Example:

```json
{
  "databases": {
    "primary": {
      "url": "$env:ECONOMY_DATABASE_URL",
      "pool_size": 20,
      "max_overflow": 40
    }
  }
}
```

Do not place real secrets in committed JSON. Reference `.env`/host environment instead.

## Multiple databases in one app

```json
{
  "databases": {
    "primary": {"url":"$env:PRIMARY_DB"},
    "analytics": {"url":"$env:ANALYTICS_DB"}
  },
  "mongo_databases": {
    "documents": {
      "uri":"$env:MONGO_URL",
      "database":"myapp"
    }
  }
}
```

A SQL resource or RPC chooses `database:"primary"`/`analytics`; a Mongo resource chooses a Mongo alias. Different apps may use completely different servers.

## Generated prefixes

Default:

```text
/api/<slug>/v1
```

So folders may produce:

```text
/api/economy/v1/...
/api/social/v1/...
/api/game/v1/...
```

Override `api_prefix` only when needed. Prefixes and slugs must be unique.

## JSON Schema/editor support

`schemas/project.schema.json` validates a complete project file. `schemas/fragment.schema.json` validates partial config fragments. Example files include `$schema` so capable editors can offer completion and early validation.

Use:

```bash
python forge.py validate
```

before deployment. `python forge.py routes` prints generated routes without starting the server.
