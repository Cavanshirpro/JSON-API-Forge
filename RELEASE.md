# JSON API Forge v0.1.0

**Release date:** 7 August 2026  
**Status:** Historical release  
**License:** JSON API Forge Source-Available Self-Host License 1.1 (`LicenseRef-JAF-SASH-1.1`)

Initial configuration-driven FastAPI backend foundation.

## Highlights

- Configuration-driven FastAPI application factory and automatic OpenAPI documentation.
- Async SQLAlchemy support for PostgreSQL/Supabase, MySQL/MariaDB and SQLite.
- Multiple database aliases and JSON-declared/reflected resources.
- API-key authentication, bootstrap administrator key, RBAC, wildcard permissions and role inheritance.
- Declarative CRUD policies, filtering, sorting, pagination, tenant columns and optional soft deletion.
- Custom Python hooks for business logic that should not be represented as generic JSON.
- Request IDs, security headers, CORS, in-memory rate limiting and cPanel Passenger compatibility.

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

- Single-project configuration model under app/config/.
- Rate limiting is primarily process-local; distributed Redis-based controls arrive in v0.2.0.
- Media, messaging/social/gaming packs, advanced cache layers and multi-project isolation are not part of this release.
- Use Alembic or another explicit migration workflow for long-lived production schemas.

## License model

The source is public for transparency, review and auditing, and official releases may be self-hosted and privately modified. This is **not an OSI-approved open-source license**: redistribution of JSON API Forge or modified/alternative versions is not permitted except for the narrow contribution-fork exception described in `LICENSE`.

Read `LICENSE`, `LICENSE-FAQ.md`, `NOTICE.md` and `GOVERNANCE.md` before redistribution-related use.

## GitHub Release asset

Attach the Project-Owner-published `JSON-API-Forge-v0.1.0-GitHub.zip` archive to the GitHub Release if you want a canonical downloadable artifact in addition to GitHub's automatically generated source archives.
