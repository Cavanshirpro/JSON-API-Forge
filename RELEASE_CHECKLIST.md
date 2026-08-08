# Release Checklist

This checklist is for Cavanşir Qurbanzadə (`@Cavanshirpro`) and future authorized maintainers of the canonical repository.

## Version and source

- [ ] `VERSION`, `pyproject.toml`, client package metadata, `CHANGELOG.md` and `RELEASE.md` match the intended tag.
- [ ] `forge validate` succeeds.
- [ ] `forge doctor` reports no errors.
- [ ] `forge doctor --production` has been run against a representative production configuration with real secrets supplied outside Git.
- [ ] `forge schema` produces no uncommitted schema drift.
- [ ] Python sources compile with `python -m compileall -q framework app tests`.

## Tests and build gates

- [ ] Python 3.11/3.12/3.13/3.14 CI jobs are green.
- [ ] `forge migrate` was exercised in the live SQL integration environment and production startup can use schema `validate` mode after migration.
- [ ] Aggregate branch-aware coverage is >=75%.
- [ ] `python scripts/check_critical_coverage.py coverage.json` passes its file-specific floors (>=80% for high-risk runtime modules and >=75% for `framework/routers/project.py`).
- [ ] Critical security/reliability paths were reviewed, not only the aggregate percentage.
- [ ] PostgreSQL transaction/idempotency tests pass against a real PostgreSQL service.
- [ ] Redis distributed rate-limit/locking tests pass against a real Redis service.
- [ ] MongoDB CRUD/tenant isolation tests pass against a real MongoDB service.
- [ ] TypeScript reference client type-checks.
- [ ] Python wheel/sdist build succeeds.
- [ ] Docker image builds successfully.
- [ ] CodeQL/security automation is not red.
- [ ] No official tag is published while required CI is red.

## Security and release hygiene

- [ ] `.env`, credentials, private keys, database files, logs, caches, local media, `.coverage`, `.pytest_cache`, `__pycache__`, build directories and egg-info are absent from the release tree.
- [ ] `.env.example` contains no usable secret value.
- [ ] Bootstrap behavior, credential delegation/impersonation, API-key auth-cache TTL, owner/tenant policies, public endpoints, proxy trust, rate budgets and idempotent operations were reviewed for configuration mistakes.
- [ ] Documentation does not claim cross-system exactly-once semantics, durable realtime delivery, unimplemented object-storage support, or attacker-safe arbitrary SQL execution.
- [ ] `LICENSE`, `NOTICE.md`, `LICENSE-FAQ.md`, `OWNERSHIP.md`, `AUTHORS.md` and contributor documents are present.
- [ ] Dependency changes and GitHub security alerts were reviewed.
- [ ] Canonical repository links and owner/successor details are accurate.
- [ ] `MANIFEST.sha256` is regenerated only after all source/doc changes and cleanup are complete.

## Publish

- [ ] Commit the intended v0.4.0 tree to `main` after v0.3.0 history.
- [ ] Push `main` and confirm CI is green.
- [ ] Create annotated tag `v0.4.0` from that exact commit.
- [ ] Push the tag and wait for the tag release gate to succeed.
- [ ] Publish the GitHub Release using `RELEASE.md` as the release body.
- [ ] Prefer GitHub's source ZIP/tar.gz for source-only distribution; add owner-published wheel/sdist or container references only when intentionally supported.
- [ ] If attaching a custom archive/binary, include SHA-256 and preferably provenance/signature/attestation.
