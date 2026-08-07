# Multi-project configuration

A project is a folder directly under `app/`.

```text
app/MyGame/
  app.json
  config/
    10-db.json
    20-security.json
    30-resources.json
    40-game.json
  hooks/
```

The root file supplies identity and any settings you want. Files under `config/` are optional and are applied alphabetically. This makes numbering useful when one fragment intentionally overrides another.

Merge rules:

- object + object → recursive merge
- array + array → append
- scalar → later value replaces earlier value

Environment references use `$env:NAME` or `$env:NAME:-default`.

Typical split:

- `10-databases.json` — DB URLs and pool sizes
- `20-security.json` — bootstrap key, roles and permissions
- `30-performance.json` — cache, limiter and protection
- `40-resources.json` — table/API definitions
- `50-features.json` — media/messaging/social/gaming
- `60-custom-endpoints.json` — hook routes

Generated API prefix defaults to `/api/<slug>/v1`, but may be changed per project.
