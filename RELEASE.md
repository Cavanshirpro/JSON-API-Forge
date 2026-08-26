# JSON API Forge Python SDK v0.5.0

**Release candidate date:** 25 August 2026

**Status:** Alpha
**Distribution:** universal pure-Python wheel and source distribution

v0.5.0 introduces typed synchronous/asynchronous Forge clients, bounded retry and pagination behavior, multi-endpoint clusters, optional YoungLion/DDM adapters and dedicated Editor control-plane clients.

The control-plane layer supports profiles, roles, scoped projects/documents/databases, project spaces, messages, notes, attachments, calls and audit. This release also tightens exact token validation, same-origin call handoff, symlink-safe bounded attachment snapshots and durable atomic downloads.

The `python-library` branch is SDK-only. Server code is owned by `main`; the Qt application is owned by `Editor`; examples are owned by `exampleApps`. CI enforces that boundary and runs a separate cross-branch contract test.

The Action uploads wheel, sdist, source ZIP and SHA-256 checksums for owner-controlled manual publication. It never pushes to PyPI or creates a GitHub Release.

JSON API Forge is source-available, not OSI open source. Official publication authority remains with Cavanşir Qurbanzadə (`@Cavanshirpro`) or a lawful successor/assignee.
