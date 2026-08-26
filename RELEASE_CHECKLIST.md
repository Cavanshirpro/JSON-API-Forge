# Release Checklist — v0.5.0

This checklist is for the Project Owner and authorized maintainers of the canonical repository.

## Version and source
- [ ] `VERSION`, `pyproject.toml`, Python/TypeScript/Editor metadata, `CITATION.cff`, `CHANGELOG.md`, `README.md` and `RELEASE.md` identify v0.5.0 where current-version metadata is intended.
- [ ] `main` has an empty `app/`; a temporary `forge new` project validates successfully.
- [ ] `forge doctor` reports no errors.
- [ ] `forge doctor --production` is exercised with representative production secrets supplied outside Git.
- [ ] `forge schema` creates no schema drift.
- [ ] `python -m compileall -q framework app tests scripts` succeeds.
- [ ] `python scripts/check_manifest.py` succeeds from the tracked release tree.
- [ ] `main` contains no Editor, Python SDK or example-app source/workflows; each specialized branch passes its ownership preflight.

## Tests and build gates
- [ ] Python 3.11/3.12/3.13/3.14 jobs are green.
- [ ] Aggregate branch-aware coverage and high-risk per-module coverage gates pass.
- [ ] PostgreSQL transaction/idempotency and migration tests pass against PostgreSQL 17.
- [ ] Redis distributed limiter/event tests pass against Redis 8.
- [ ] Mongo CRUD/tenant isolation tests pass against MongoDB 8.
- [ ] TypeScript reference client type-checks on Node 22 / TypeScript 7.
- [ ] Wheel/sdist build succeeds.
- [ ] Python library retry/failover, bounded bulk and YoungLion/DDM integration tests pass.
- [ ] Editor CMake tests and screenshot smoke tests pass on Linux, Windows and macOS x64/ARM64.
- [ ] All 25 example projects pass generator, schema, CRUD, RPC, idempotency and realtime smoke checks.
- [ ] Docker image builds.
- [ ] CodeQL is not red.
- [ ] No official tag is published while required CI is red.

## Security / hygiene
- [ ] No `.env`, credentials, keys, DBs, logs, local media, caches, coverage output, build output or `__pycache__` exists in the release tree.
- [ ] `.env.example` contains no usable secret.
- [ ] Bootstrap, delegation, JWT/JWKS, tenant/owner policies, proxy trust, rate limits, idempotency and public endpoints are reviewed.
- [ ] Editor API remains disabled by default; setup/legacy secrets, invitation authority snapshots, request IDs, WebSocket ticket transport, TLS/IP/project/write/graph policies and the 1 MiB WebSocket ceiling are regression-tested.
- [ ] Native plugin hashes, explicit approvals and Forge catalog bounds are reviewed; no workflow auto-enables native code.
- [ ] Docs do not overclaim exactly-once external delivery, durable realtime, object-storage support or attacker-safe arbitrary SQL.
- [ ] `LICENSE`, notices, ownership and contributor documents are present.
- [ ] Dependency/security alerts are reviewed.

## Publish
- [ ] Commit the exact v0.5.0 tree to `main` after v0.4.2.
- [ ] Wait for `main` CI to pass.
- [ ] Create annotated tag `v0.5.0` from that exact commit and push it.
- [ ] Wait for the tag release gate.
- [ ] Publish the GitHub Release using `RELEASE.md`.
