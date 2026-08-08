# CLI and developer experience

v0.4 treats the CLI as part of the product surface rather than a collection of unrelated scripts.

## Installation

After installing the package:

```bash
pip install -e .
```

both of these entry points are available:

```text
forge
json-api-forge
```

The repository-root compatibility wrapper also supports:

```bash
python forge.py ...
```

## Commands

### `forge new`

Create a project skeleton:

```bash
forge new MyBot --slug my-bot --preset discord-bot
```

Presets:

- `minimal`: project structure plus empty resource list;
- `postgres-api`: a simple SQL-backed resource example;
- `discord-bot`: SQL resource plus bot role example;
- `game-backend`: SQL resource plus gaming resource pack example.

Generated applications are normal files. A preset is scaffolding, not a runtime dependency.

### `forge init`

Create `.env` safely:

```bash
forge init
```

Production-intended marker:

```bash
forge init --production
```

Forge scans application JSON files for environment references whose names look secret-sensitive and creates strong random values.

Safety rules:

- refuses to overwrite `.env` unless `--force` is supplied;
- never writes generated secrets into `.env.example`;
- attempts `0600` file permissions on POSIX;
- should be run by the deployment operator, not by untrusted code.

`--force` is effectively a local secret rotation. Existing API/JWT consumers can break when secrets rotate, so use it deliberately.

### `forge secrets`

Print random tokens for manual secret-manager workflows:

```bash
forge secrets --count 3
```

This is not a replacement for a secret manager.

### `forge validate`

```bash
forge validate
```

Validates:

- JSON syntax;
- fragment merging;
- environment expansion;
- strict typed configuration;
- model-level invariants;
- semantic diagnostics that are considered startup errors.

Use this in every CI pipeline.

### `forge doctor`

```bash
forge doctor
forge doctor --production
forge doctor --production --json
```

`doctor` is intended for actionable deployment diagnostics rather than schema parsing alone.

Machine-readable JSON output is useful for CI or an admin dashboard.

### `forge routes`

```bash
forge routes
```

Builds the application and prints generated HTTP/WebSocket route paths. This is useful when reviewing what a configuration change actually exposes.

Because route construction initializes application configuration, this command can require configured runtime dependencies/drivers.

### `forge schema`

```bash
forge schema
```

Regenerates:

```text
schemas/project.schema.json
schemas/fragment.schema.json
```

These schemas come from the typed Pydantic configuration models.

### `forge openapi`

```bash
forge openapi --output openapi.json
```

Builds the application and writes generated OpenAPI. This is useful for:

- SDK generation;
- contract review;
- API diffing;
- documentation publishing.

### `forge dev`

```bash
forge dev
forge dev --host 0.0.0.0 --port 8000
```

Development helper around Uvicorn. Do not infer production worker counts or reverse-proxy settings from the dev command.

## Recommended workflow

```text
forge new
   ↓
edit JSON with schema autocomplete
   ↓
forge init
   ↓
forge validate
   ↓
forge doctor
   ↓
pytest
   ↓
forge dev
   ↓
OpenAPI/manual verification
```

For production add:

```text
forge doctor --production
integration tests
backup/restore test
capacity/load test
staging rollout
```

## CLI exit behavior

Automation should rely on non-zero exit codes for invalid configuration/production diagnostics. Human-readable output is useful, but CI should primarily trust the exit status.

## Root selection

The CLI supports `--root` for tooling/testing against another project directory:

```bash
forge --root /path/to/checkout validate
```

This is useful for editor tasks, tests, and build systems.

## Generated code philosophy

Forge does not want to generate thousands of lines of application Python and then abandon them. The canonical model is runtime interpretation of version-controlled declarative configuration plus small explicit hooks.

That means a user can review the actual app contract in `app/<Name>/` without regenerating code after every change.

## Python client

`clients/python/json_api_forge_client.py` is a small async reference client using HTTPX. It demonstrates connection pooling and narrow API calls for bots/plugins/services.

## TypeScript client

`clients/typescript/src/index.ts` is a `fetch()`-based strict TypeScript reference client for browser/Node/Electron/tooling scenarios.

It supports:

- API key or bearer authentication;
- generic requests;
- resource list/get/create/update/delete helpers;
- RPC calls;
- idempotency headers;
- request timeout/abort;
- error status/payload/request ID propagation.

It is intentionally a reference client in this source tree, not a separately distributed alternative Forge package.

## Future DX rules

When adding a new declarative field:

1. add it to the typed model;
2. validate incompatible combinations;
3. regenerate JSON Schema;
4. add at least one focused test;
5. document its security/failure semantics;
6. make it observable through `doctor` if it creates a production risk.

This rule prevents configuration from becoming an undocumented pile of toggles.
