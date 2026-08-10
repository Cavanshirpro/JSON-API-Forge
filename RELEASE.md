# JSON API Forge v0.4.1

**Release date:** 10 August 2026  
**Status:** Alpha corrective hardening release  
**License:** JSON API Forge Source-Available Self-Host License 1.1 (`LicenseRef-JAF-SASH-1.1`)

v0.4.1 is a corrective reliability, security and release-integrity patch over v0.4.0. It deliberately keeps the same config-first architecture and feature scope while fixing defects exposed by the first v0.4 GitHub-hosted CI runs and a subsequent adversarial review.

## Fixed
- Removed legacy `app/config`, which was incorrectly discovered as a third project and broke strict validation.
- Removed obsolete root `app/hooks`; hooks are project scoped.
- Preserved the PostgreSQL fragment example under `examples/postgres-fragment.json`.
- Fixed idempotent replay output (`_idempotent_replay: true` plus response header) while keeping the persisted canonical first response unchanged.
- Prevented replayed idempotent operations from scheduling background hooks a second time.
- Replaced deprecated FastAPI `ORJSONResponse` runtime response paths with `JSONResponse` and FastAPI-compatible encoding.
- Updated Forge/project default version metadata to 0.4.1 and regenerated JSON Schemas.
- Corrected the MongoDB tenant example so the server-controlled tenant field is not client-writable.

## Security / dependencies
- `pydantic-settings>=2.14.2` to include the nested-secrets symlink security fix.
- `orjson>=3.11.9`, `SQLAlchemy>=2.0.51`, and `asyncpg>=0.31.0` align minimums with versions already exercised by the GitHub-hosted dependency resolution used during v0.4 review.

## CI / release integrity
- `actions/checkout@v7` across CI and CodeQL.
- TypeScript reference client uses TypeScript 7.0.2.
- `MANIFEST.sha256` is generated from the final release tree and CI verifies hashes plus tracked-file completeness.
- Python 3.11–3.14, PostgreSQL 17 + Redis 8 + MongoDB 8 integration, TypeScript, Docker and CodeQL remain required release gates.

## Compatibility
v0.4.1 is intended as a patch release for v0.4.0. Existing numbered multi-project JSON configuration remains the primary architecture. The v0.3 compatibility feature tests remain part of the suite. Configurations depending on obsolete root-level `app/config` or `app/hooks` should be moved into an explicit `app/<Project>/` project structure.

## Important boundaries
JSON API Forge remains Alpha. Transactional idempotency applies to side effects in the selected SQL database, not external APIs or a second system. Realtime is best-effort. Local filesystem is the implemented media backend. Declarative SQL is trusted configuration rather than an attacker-safe SQL sandbox. Native ASGI is preferred for sustained realtime workloads.

## Official distribution
JSON API Forge is source-available for transparency, auditing, self-hosting and private modification. It is not OSI open source. Alternative distributions remain restricted by `LICENSE`; official release authority remains with Cavanşir Qurbanzadə (`@Cavanshirpro`) or a lawful successor/assignee.
