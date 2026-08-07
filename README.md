# JSON API Forge v0.2.0

**Creator / current project owner:** Cavanşir Qurbanzadə ([@Cavanshirpro](https://github.com/Cavanshirpro))  
**Canonical repository:** https://github.com/Cavanshirpro/JSON-API-Forge  
**License:** JSON API Forge Source-Available Self-Host License 1.1 — source-available, not OSI open source.


![Version](https://img.shields.io/badge/version-0.2.0-blue) ![License](https://img.shields.io/badge/license-source--available-orange) ![FastAPI](https://img.shields.io/badge/runtime-FastAPI-009688)

> **Historical release.** Multi-project runtime with production-oriented cache, rate limits, media and application feature packs.

JSON API Forge is a configuration-driven backend runtime built around FastAPI. Its long-term goal is to move reusable backend infrastructure—database routing, API policies, authentication, authorization, caching, limits, resource definitions and integration behavior—into application configuration under `app/`, while reserving Python hooks for logic that genuinely needs code.

## License at a glance

JSON API Forge is **source-available, not OSI open source**. You may inspect the source, self-host official releases, use them commercially, and privately modify them for your own deployment. You may **not redistribute** the framework or publish an alternative modified/unmodified distribution, package, image or maintained fork, except for the narrow contribution-fork workflow described in `LICENSE`.

See [`LICENSE`](LICENSE), [`LICENSE-FAQ.md`](LICENSE-FAQ.md), [`NOTICE.md`](NOTICE.md), [`OWNERSHIP.md`](OWNERSHIP.md), [`AUTHORS.md`](AUTHORS.md), and [`GOVERNANCE.md`](GOVERNANCE.md).

## Release information

- Version: **0.2.0**
- Release notes: [`RELEASE.md`](RELEASE.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Publishing all three historical releases: [`GITHUB_PUBLISHING.md`](GITHUB_PUBLISHING.md)
- Release asset guidance: [`RELEASE_ASSETS.md`](RELEASE_ASSETS.md)
- Ownership and future company transfer: [`OWNERSHIP.md`](OWNERSHIP.md)

---

JSON API Forge is a **multi-project, JSON-defined FastAPI backend runtime**. The framework code lives in `framework/`; application-specific work lives under `app/<Project>/`. A project can be split across as many JSON fragments as needed.

```text
app/
├── App1/
│   ├── app.json
│   ├── config/
│   │   ├── 10-databases.json
│   │   ├── 20-security.json
│   │   ├── 30-performance.json
│   │   ├── 40-resources.json
│   │   ├── 50-features.json
│   │   └── 60-custom-endpoints.json
│   └── hooks/
└── App2/
    └── app.json
```

The loader reads `app.json`/`manifest.json`, then merges every `config/*.json` in lexical order. Dictionaries merge recursively, arrays append, and later scalar values override earlier values. This lets a large backend be treated almost like a declarative language: database, permissions, resources, cache policy, rate limits and feature packs are configuration; unusual business rules are small Python hooks.

## What changed in 0.2

- Multiple independent projects under one runtime: `app/App1`, `app/App2`, ...
- Each project may use multiple JSON fragments.
- Independent API prefixes, databases, API keys, roles, policies and feature packs.
- Connection-pool tuning for PostgreSQL/MySQL.
- Memory, Redis and two-tier L1+L2 cache backends.
- Generation-based cache invalidation; mutations never scan thousands of cache keys.
- Stampede protection inside a worker for expensive cache misses.
- Redis or in-memory token-bucket rate limiting with burst capacity.
- Per-API-key rate overrides and tenant binding for third-party plugins/clients.
- Concurrency gate, bounded queue wait, request timeout and body-size protection.
- Project-aware CORS instead of one global CORS permission set.
- IP allow/deny lists and optional HTTPS enforcement.
- Batched asynchronous audit writer so audit INSERTs do not sit on the request hot path.
- Readiness checks for every configured database.
- GZip and security response headers.
- Media upload/download/metadata/delete API with MIME allowlist, maximum size, SHA-256 digest, deduplication and safe filenames.
- Messaging feature pack: conversations, members, messages, reactions and receipts.
- Social feature pack: profiles, posts, comments, reactions, follows and notifications.
- Gaming feature pack: players, saves, inventory, achievements, leaderboards and sessions.
- Cursor/keyset pagination support for high-volume ordered resources; messaging messages and social posts use it by default.
- Reusable outbound `ResilientHTTPClient` with pooling, retry/backoff and circuit breaker.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/generate_secret.py
python scripts/validate_config.py
python run.py
```

Then open `/docs`, `/health`, and `/ready`.

App1 example prefix is `/api/app1/v1`; App2 is `/api/app2/v1`.

## Production cache mode

For a single worker, memory cache is fine. For multiple workers or multiple servers, use Redis:

```json
{
  "cache": {
    "enabled": true,
    "backend": "tiered",
    "default_ttl_seconds": 30,
    "max_entries": 20000
  },
  "rate_limit": {
    "enabled": true,
    "backend": "redis",
    "requests": 1200,
    "window_seconds": 60,
    "burst": 200
  }
}
```

`tiered` means an L1 in-process cache backed by shared Redis. Resource mutations increment a generation counter; future cache keys use the new generation immediately. Old keys simply expire naturally.

## Feature packs

One JSON fragment can create a large family of APIs:

```json
{
  "features": {
    "messaging": {"enabled": true, "database": "primary", "table_prefix": "msg_"},
    "social": {"enabled": true, "database": "primary", "table_prefix": "social_"},
    "gaming": {"enabled": true, "database": "primary", "table_prefix": "game_"}
  }
}
```

These packs generate reusable storage/API primitives. They deliberately do **not** pretend that every application's business rules are identical. Rules such as "only conversation members may send messages", feed ranking, anti-cheat score verification or payment settlement should be implemented as hooks/services rather than blindly trusting generic CRUD.

## Security rule

Never commit real secrets in JSON. Use environment references:

```json
{"bootstrap_admin_key": "$env:APP1_BOOTSTRAP_ADMIN_KEY"}
```

API keys are returned once and stored as hashes. Give every plugin its own key and minimum permissions.

## Documentation

Start with:

- `docs/01-Architecture.md`
- `docs/02-Multi-Project-Configuration.md`
- `docs/03-Performance-and-Cache.md`
- `docs/04-Security-and-Protection.md`
- `docs/05-Media.md`
- `docs/06-Messaging-Social-Gaming.md`
- `docs/07-Production-Scaling.md`
- `docs/cPanelGuide.md`

## Important boundary

This project is a strong framework foundation, not a magical replacement for domain logic. JSON is excellent for infrastructure and policy; security-sensitive business invariants still belong in code and tests. For serious production schema evolution, use Alembic migrations instead of relying on `auto_create` after the schema is live.

## Repository policy

Only Cavanşir Qurbanzadə (@Cavanshirpro), or a lawful successor/assignee, may designate Official Releases or authorize alternative distribution. External contributions are welcome through the canonical repository subject to the CLA and project governance. Do not commit `.env`, credentials, database files, private keys, production logs or sensitive user data.