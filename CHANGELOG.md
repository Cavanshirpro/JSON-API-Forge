# Changelog

## 0.5.0 — 2026-08-25

- Split `exampleApps` into an example-only distribution with no copied server, SDK or Editor source.
- Added 25 named, copy-ready projects covering CRUD, roles, SQL/RPC, idempotency, realtime, media, public data and Editor graph metadata.
- Added 20 deterministic large-domain systems with four resources, three operations and scoped workflow policies each.
- Added `EditorPluginRegistry` for bounded reviewed plugin metadata without automatic native-code execution.
- Added safe Bash and PowerShell one-project installers.
- Added a deterministic bounded ZIP builder with internal and external SHA-256 inventories.
- Added Python 3.11–3.14 smoke tests that copy the examples into a separately checked-out `main` runtime.
- Added native Linux/Windows installer tests, branch-ownership enforcement, manifest verification and CodeQL.
