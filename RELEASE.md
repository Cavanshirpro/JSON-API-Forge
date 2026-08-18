# JSON API Forge v0.4.2

**Release date:** 18 August 2026

**Status:** Alpha hardening and tooling release

**License:** JSON API Forge Source-Available Self-Host License 1.1 (`LicenseRef-JAF-SASH-1.1`)

v0.4.2 preserves the numbered JSON/FastAPI architecture while hardening configuration, credential delegation, outbound networking and realtime accounting. `main` is now a clean runtime distribution with no bundled applications.

## Security and correctness

- Reserved/legacy/hidden `app/` support folders are never interpreted as projects.
- Project names/slugs, API prefixes and configurable HTTP headers reject traversal and control ambiguity.
- Controlled outbound HTTP and JWKS retrieval do not inherit ambient proxy variables.
- Expired API keys are not cached, unknown delegated roles are rejected, and delegated sustained request rate cannot exceed the issuer.
- WebSocket connection slots are reserved atomically.
- The editor control plane is absent by default and uses an independent token plus TLS, IP, trusted-proxy, project, read-only, creation and hook policies.
- Editor writes use SHA-256 optimistic concurrency, whole-project staged validation and atomic file replacement.

## Distribution and developer experience

- `main` contains no example project. `forge new` creates the first app; named copy-ready projects live on `exampleApps`.
- `forge new` now rejects path traversal, generates correct project/fragment schema links and writes schemas when installed from Git/wheel.
- `forge dev` works in a standalone directory after direct Git/wheel installation.
- Linux/macOS and PowerShell setup scripts provide an isolated `.venv` workflow.
- `python-library`, `Editor` and `exampleApps` carry branch-specific CI/artifact workflows; nothing auto-publishes.

## Required gates

Python 3.11–3.14, Ruff, branch coverage and critical-module gates, PostgreSQL 17, Redis 8, MongoDB 8, isolated wheel installation, TypeScript/Node 22, Docker, release-manifest verification and CodeQL must pass before an official tag.

## Compatibility and limits

Existing explicit `app/<Project>/` numbered configurations remain the primary architecture. Legacy root-level `app/config` and `app/hooks` are ignored and should be migrated. JSON API Forge remains Alpha: same-database idempotency is not external exactly-once delivery, realtime is not durable, local media is not shared object storage, and declarative SQL is trusted configuration rather than an attacker-safe sandbox.

## Official distribution

JSON API Forge is source-available for transparency, auditing, self-hosting and private modification. It is not OSI open source. Alternative distributions remain restricted by `LICENSE`; official release authority remains with Cavanşir Qurbanzadə (`@Cavanshirpro`) or a lawful successor/assignee.
