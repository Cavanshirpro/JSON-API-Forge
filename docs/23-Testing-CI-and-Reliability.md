# Testing, CI and reliability

JSON API Forge is infrastructure. Route-count demonstrations are not enough evidence of reliability. v0.4 therefore separates fast deterministic tests from live-service integration tests and release gates.

## Test pyramid

### Level 1: configuration/model tests

Fast tests for:

- strict parsing;
- fragment merge behavior;
- environment expansion;
- default-private security rules;
- incompatible setting validation;
- JSON Schema generation.

### Level 2: component tests

Tests without external services for:

- memory cache behavior;
- cache generation invalidation;
- single-flight/stale refresh behavior;
- memory rate-limit bounding/cleanup;
- concurrency gate behavior;
- ASGI streaming body limits;
- file data source locking/mutation/path safety;
- local media streaming/path/signed token behavior;
- event hub/WebSocket cleanup;
- SQL helper/parameter resolution;
- audit queue pressure/retry behavior;
- Mongo helper behavior using controlled fake collections.

### Level 3: application integration tests

Start a real FastAPI app and send HTTP requests through the generated routes.

These tests exercise boundaries that pure function tests cannot:

- middleware order;
- authentication + permission + route behavior;
- generated CRUD/OpenAPI;
- cache invalidation after write;
- media endpoints;
- streamed request bodies;
- bootstrap consumption.

### Level 4: real service integration tests

CI provisions real services for:

- PostgreSQL;
- Redis;
- MongoDB.

Critical test examples include:

- PostgreSQL idempotent transfer replay and rollback;
- same idempotency key + changed payload conflict;
- shared Redis rate-limit budget across separate limiter instances;
- MongoDB CRUD and tenant isolation.

### Level 5: pre-production validation

Repository CI cannot prove your deployment topology. Operators should additionally run:

- load tests;
- backup/restore tests;
- process kill/restart tests;
- dependency outage tests;
- network timeout tests;
- reverse-proxy/TLS validation;
- database migration rehearsal.

## Python version matrix

CI targets the supported runtime floor and current supported interpreters:

```text
Python 3.11
Python 3.12
Python 3.13
Python 3.14
```

A release tag should not be treated as healthy when only one interpreter passes.

## Service-container job

The integration workflow uses separate PostgreSQL, Redis, and MongoDB service containers. Environment variables tell tests where those disposable services live.

The important distinction is:

```text
unit tests skipped because Redis is absent != Redis integration passed
```

A local environment can legitimately skip service tests; the release gate must still execute them in an environment where the dependencies exist.

## Coverage

Coverage is a signal, not a correctness proof. v0.4 uses **two separate gates** so a broad but shallow test suite cannot hide weak security/reliability code:

1. `pyproject.toml` enforces a **75% aggregate branch-aware coverage floor** for the `framework` package.
2. `scripts/check_critical_coverage.py` enforces file-specific floors: **>=80%** for the high-risk runtime set (audit, cache, CRUD, data sources, database, events, factory, media, MongoDB, observability, SQL/RPC operations, request protection, rate limiting, runtime lifecycle, security and the resilient outbound HTTP client) and **>=75%** for the large generated project-router assembly surface.

The canonical local command is:

```bash
pytest \
  --cov=framework \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-report=json:coverage.json \
  -q
python scripts/check_critical_coverage.py coverage.json
```

The critical-module gate is intentionally independent of the aggregate percentage. It should fail if, for example, authorization, lifecycle cleanup or application assembly drops below its file-specific threshold even when CLI or schema tests keep the package-wide number high.

The more important rule remains **critical-path coverage**, especially for:

- authentication and authorization;
- tenant filtering;
- SQL transaction rollback;
- idempotency;
- request-body limits;
- rate limiting;
- cache invalidation;
- media ownership/path handling;
- audit failure behavior.

A high percentage produced by testing getters while transaction code remains untested is not acceptable evidence.

## Concurrency testing

Concurrency bugs are often absent in a single sequential test.

Target cases:

- many simultaneous cache misses for the same key;
- two requests with the same idempotency key;
- multiple file mutations;
- several WebSocket publishers/subscribers;
- rate-limit checks from multiple processes/clients;
- service shutdown while audit work remains queued.

## Idempotency reliability test pattern

A financial-style operation should verify at minimum:

1. first request changes state exactly once;
2. retry with same key and same request replays the result;
3. retry with same key and different request returns conflict;
4. a failing statement rolls the whole SQL transaction back;
5. after success, business state and idempotency result are committed together.

Cross-system side effects require separate architecture tests.

## Security regression tests

Every previously identified security issue should become a regression test where practical.

Examples:

- known/default secret rejected by production doctor;
- operation with no permission/public flag rejected;
- public read does not imply public write;
- raw dynamic path does not generate a new principal-global rate bucket;
- memory bucket collection is bounded;
- oversized chunked request is rejected;
- tenant A cannot read/update tenant B row/document.

## CI gates

The repository workflow conceptually enforces:

```text
checkout
  ↓
install
  ↓
validate / doctor / schema drift
  ↓
compile / dependency graph check
  ↓
unit + coverage
  ↓
package build

parallel:
real PostgreSQL + Redis + Mongo integration

parallel:
TypeScript client typecheck
Docker image build

release tag:
Python matrix AND live-service integration AND TypeScript AND container build must succeed
```

Do not publish a release from a known-red release commit and then describe the release as production-ready.

## Schema drift

Configuration schema is generated from code. CI runs schema generation and checks whether committed schemas change.

If a contributor changes a model but forgets the generated schema, CI should fail.

## Package build

CI builds the Python distribution metadata/artifacts to catch packaging errors independent of application tests.

Local check:

```bash
python -m build
```

or:

```bash
python -m pip wheel --no-deps --no-build-isolation .
```

## TypeScript reference client

The TypeScript client should remain strict-type-checkable:

```bash
tsc -p clients/typescript/tsconfig.json
```

## Load testing

`scripts/load_test.py` provides a simple concurrency/latency probe. It is not a full performance laboratory.

Use production-like data, DB indexes, network paths and worker counts before interpreting RPS numbers.

Record:

- concurrency;
- requests/second;
- p50/p95/p99;
- error status distribution;
- DB pool saturation;
- Redis latency;
- CPU/memory;
- open connections;
- event loop lag if available.

## Release evidence

A mature release should eventually be able to state evidence such as:

- green CI commit SHA;
- tested Python versions;
- live service versions;
- coverage report;
- migration test status;
- load-test scenario;
- security-review status.

Avoid vague claims such as “enterprise grade” without measurable evidence.


## What local skips mean

The default suite is written so deterministic component tests remain useful on machines without PostgreSQL, Redis or MongoDB drivers/services. Tests marked as live-service integrations may therefore skip locally. That is an environment distinction, not a success result.

Before publishing a tag, the canonical GitHub workflow must execute the live-service job with PostgreSQL 17, Redis 8 and MongoDB 8 service containers. A release should record **both** the local deterministic result and the required green hosted integration result rather than merging them into one ambiguous number.

## Coverage regression policy

When a security or reliability defect is fixed, add a regression test before or with the fix whenever practical. Do not lower the per-critical-module threshold merely to merge a change. If a module genuinely needs an exception, document the untested boundary, open follow-up work and keep the exception visible in review instead of silently weakening the global gate.
