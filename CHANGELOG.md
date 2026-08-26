# Changelog

## 0.5.0 — 2026-08-25

- Split the Python SDK into the independent `json-api-forge-client` pure-Python distribution.
- Added typed synchronous/asynchronous CRUD, operation and general request clients.
- Added capped retries, request-attempt observability and bounded pagination.
- Added multi-endpoint routing, circuit breakers, endpoint health and bounded bulk execution.
- Required idempotency keys before retrying or failing over writes.
- Added optional YoungLion/DDM adapters without expanding the base dependency set.
- Added synchronous/asynchronous Editor control-plane clients for accounts, roles, projects, documents, databases, collaboration, attachments, calls and audit.
- Hardened URLs, redirects, ambient proxy/cookie behavior, token formats, response bounds, upload snapshots and atomic downloads.
- Added SDK-only ownership gates, Python/platform matrices, Linux distribution installs, CodeQL, coverage, reproducible-package checks and a real contract test against `main`.
