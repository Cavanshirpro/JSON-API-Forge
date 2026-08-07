# JSON API Forge v0.2.0

**Release date:** 7 August 2026  
**Status:** Historical release  
**License:** JSON API Forge Source-Available Self-Host License 1.1 (`LicenseRef-JAF-SASH-1.1`)

Multi-project runtime with production-oriented cache, rate limits, media and application feature packs.

## Highlights

- Multiple independent applications under app/<Project>/ with mergeable JSON fragments.
- Per-project API prefixes, databases, credentials, roles, CORS policies and feature packs.
- Memory, Redis and tiered L1/L2 caches with generation-based invalidation.
- Token-bucket rate limiting, per-key traffic budgets and concurrency/backpressure protection.
- Database connection-pool tuning, readiness checks and batched asynchronous audit writes.
- Media APIs with streaming upload, MIME/size policies, hashing and deduplication.
- Messaging, social-media and gaming resource packs.
- Cursor/keyset pagination and resilient outbound HTTP client foundation.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Generate strong secrets before starting the server. Never use the placeholder values from `.env.example` in production.

## Validate this release

```bash
python scripts/validate_config.py
python -m compileall -q framework app
pytest -q
```

## Known boundaries

- The declarative SQL/RPC operation engine and arbitrary JSON/YAML/CSV data sources arrive in v0.3.0.
- Realtime WebSocket/SSE channels and external JWKS/Supabase Auth integration arrive in v0.3.0.
- Local filesystem is the implemented media storage backend in this release.
- For serious WebSocket/realtime scale, use native ASGI rather than the cPanel WSGI bridge.

## License model

The source is public for transparency, review and auditing, and official releases may be self-hosted and privately modified. This is **not an OSI-approved open-source license**: redistribution of JSON API Forge or modified/alternative versions is not permitted except for the narrow contribution-fork exception described in `LICENSE`.

Read `LICENSE`, `LICENSE-FAQ.md`, `NOTICE.md` and `GOVERNANCE.md` before redistribution-related use.

## GitHub Release asset

Attach the Project-Owner-published `JSON-API-Forge-v0.2.0-GitHub.zip` archive to the GitHub Release if you want a canonical downloadable artifact in addition to GitHub's automatically generated source archives.
