# JSON Schema and IDE setup

A declarative backend is only pleasant to use when configuration errors are discoverable before the server starts. v0.4 makes the typed Pydantic configuration models the source for editor-facing JSON Schema.

## Generated schemas

Run:

```bash
forge schema
```

Forge writes:

```text
schemas/project.schema.json
schemas/fragment.schema.json
```

`project.schema.json` represents a fully merged `ProjectConfig`. `fragment.schema.json` is intentionally more permissive at the root because a fragment can contain any subset of project fields, while the nested values still use the same typed model definitions.

Do not hand-edit generated schema files. Change `framework/config.py`, regenerate, test, and commit both code and schema changes.

## Why strict models matter

All Forge config models inherit from a strict base model with `extra="forbid"`.

Therefore this typo:

```json
{
  "protection": {
    "max_concurent_requests": 100
  }
}
```

fails instead of silently falling back to a default because the correct field is `max_concurrent_requests`.

This is especially important for security fields where a typo can otherwise become an accidental policy change.

## `$schema` in project files

Project files may include editor metadata:

```json
{
  "$schema": "../../../schemas/fragment.schema.json",
  "rate_limit": {
    "requests": 300,
    "window_seconds": 60
  }
}
```

The runtime removes the root `$schema` field before Pydantic validation.

## VS Code

The repository includes `.vscode/settings.json` with associations for:

```text
app/*/app.json
app/*/manifest.json
app/*/config/*.json
```

VS Code can then provide:

- completion for field names;
- enum suggestions;
- type validation;
- minimum/maximum constraint hints;
- descriptions from schema/model metadata where present;
- unknown-property errors.

The files are ordinary JSON, not JSON-with-comments. Do not rely on `//` comments inside runtime config.

### Explicit per-file schema

You can also keep `$schema` in each JSON file. This is useful when a contributor opens the file outside the repository workspace.

Example project manifest:

```json
{
  "$schema": "../../schemas/fragment.schema.json",
  "slug": "bot",
  "name": "Bot API",
  "databases": {
    "primary": {
      "url": "$env:BOT_DATABASE_URL:-sqlite+aiosqlite:///./data/bot.db"
    }
  }
}
```

## PyCharm / JetBrains IDEs

JetBrains IDEs can associate a JSON Schema with path patterns through the JSON Schema Mappings settings.

Recommended mapping concept:

```text
schemas/project.schema.json
  -> app/*/app.json
  -> app/*/manifest.json

schemas/fragment.schema.json
  -> app/*/config/*.json
```

The exact UI name/location can vary by IDE version. If workspace mapping is unavailable, keep the `$schema` field directly in the JSON file.

## Schema does not replace semantic validation

JSON Schema catches structure and many constraints, but some rules depend on relationships across the merged project.

Examples:

- database alias referenced by a resource exists;
- a dependency name exists;
- two generated method/path pairs do not collide;
- a production secret is actually strong;
- a Redis-backed feature has a Redis URL.

Therefore the correct workflow is:

```text
IDE schema
    ↓
forge validate
    ↓
forge doctor
    ↓
forge doctor --production
```

## Environment references

The schema treats many values as strings, so environment expressions are valid config values:

```json
{
  "url": "$env:APP_DATABASE_URL:-sqlite+aiosqlite:///./data/app.db"
}
```

Syntax:

```text
$env:NAME
$env:NAME:-default-value
```

Avoid defaults for credentials. Defaults are appropriate for non-secret local convenience values such as a development SQLite URL.

## Improving autocomplete when adding a feature

When developing Forge itself:

1. create/update the Pydantic model field;
2. use `Literal[...]` for a closed set of strings;
3. use `Field(ge=..., le=...)` for numeric constraints;
4. use model validators for cross-field invariants;
5. add docstrings/comments where semantics are not obvious;
6. run `forge schema`;
7. test invalid and valid configurations;
8. confirm the IDE marks invalid examples.

## Schema CI

CI runs schema generation and then checks for uncommitted schema drift. A PR that changes config models but does not update `schemas/` should fail the schema-drift step.

## Future editor tooling

Potential future enhancements include:

- an official editor extension;
- hover documentation generated from Forge docs;
- schema versions tied to Forge releases;
- quick fixes for deprecated config fields;
- route/permission references across fragments.

These are roadmap ideas, not v0.4 runtime features.
