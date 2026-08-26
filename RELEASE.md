# JSON API Forge v0.5.0

**Release date:** 18 August 2026

**Status:** Alpha visual-authoring and integration release

**License:** JSON API Forge Source-Available Self-Host License 1.1 (`LicenseRef-JAF-SASH-1.1`)

v0.5.0 preserves the strict numbered JSON/FastAPI runtime while making large projects easier to author and integrate. `main` remains an example-free runtime; the `python-library`, `Editor` and `exampleApps` branches are independently buildable distributions.

## Runtime and Editor boundary

- The disabled-by-default Editor control plane now supports `graphs/*.forgegraph.json` only when `EDITOR_ALLOW_GRAPHS=true`.
- Graph documents have exact fields, bounded node/edge counts, direct config targets, safe identifiers, unique input fan-in and acyclic execution.
- A graph is Editor metadata: compiled configuration must still pass the normal whole-project schema and semantic validation.
- Existing independent editor token, TLS, trusted-proxy/IP, project allowlist, read-only, creation, hook, size, optimistic-concurrency and atomic-write controls remain enforced.

## Qt Editor

- C++20/Qt 6 code, typed visual and Unreal-inspired graph modes.
- Draggable nodes, Bézier wires, pan/zoom, selection/deletion, inspector JSON, validation, auto-layout, fit-to-content and compiled operation preview.
- Eight staged/atomic project templates and a Python SDK panel for sync, async, cluster, YoungLion and DDM usage.
- Native Plugin API v2 with explicit enablement, SHA-256 verification, declared permissions and plugin graph-node registration.
- A bounded catalog browser backed by a normal JSON API Forge resource; native packages are never silently downloaded or executed.
- Native build/test artifacts for Linux, Windows and macOS on x64 and ARM64.

## Python library

- Typed sync and async clients with capped retries, stable request IDs, bounded response/pagination behavior and attempt observers.
- Multi-region sync/async clusters with deterministic routing, circuit breaking, health inspection and bounded bulk work.
- Unsafe writes are not retried or failed over without an idempotency key.
- Optional `json-api-forge[younglion]` and `json-api-forge[ddm]` installs provide lazy DDM adapters without adding YoungLion to the base wheel.

## Example systems

The `exampleApps` branch now contains 25 named projects. The 20 generated domain systems each include four SQL resources, three meaningful operations, scoped roles, cache/rate/protection policy, realtime events, an Editor graph and an application runbook. The full catalog is deterministically regenerated and tested across schema, CRUD, filtered list, RPC, idempotency and event lifecycles.

## Required gates

Python 3.11–3.14, Ruff, branch coverage and critical-module gates, PostgreSQL 17, Redis 8, MongoDB 8, isolated wheel installation, TypeScript/Node 22, Docker, release-manifest verification and CodeQL must pass before an official tag. Editor artifacts additionally require six native CMake/Qt builds and tests; example artifacts require all 25 project smoke scenarios.

## Compatibility and limits

Existing explicit `app/<Project>/` numbered configurations remain the primary architecture. JSON API Forge remains Alpha: same-database idempotency is not external exactly-once delivery, realtime is not durable, local media is not shared object storage, native plugins are not sandboxed, and declarative SQL is trusted configuration rather than an attacker-safe SQL sandbox.

## Official distribution

JSON API Forge is source-available for transparency, auditing, self-hosting and private modification. It is not OSI open source. Alternative distributions remain restricted by `LICENSE`; official release authority remains with Cavanşir Qurbanzadə (`@Cavanshirpro`) or a lawful successor/assignee.
