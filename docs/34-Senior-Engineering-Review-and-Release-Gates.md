# Senior Engineering Review and Release Gates

v0.4 was developed under a stricter rule: **a feature is not release-ready merely because its happy path works**.

## 1. Review questions

For every component ask:

1. What happens when an attacker controls high-cardinality input?
2. What happens when two workers race?
3. What happens if the process dies between two commits?
4. What happens if Redis/database/upstream HTTP is slow or unavailable?
5. Does a configuration option actually change runtime behavior?
6. Is the secure behavior the default?
7. Can one project cross another project's trust boundary?
8. Does documentation match runtime semantics?
9. Can state grow forever in a month-long process?
10. Can the feature be monitored when it degrades?

## 2. Release blockers

A v0.4 release must not be tagged when any of these are known:

- failing unit/component tests;
- failing critical coverage gate;
- invalid generated JSON Schema;
- `forge validate` failure;
- production doctor errors for the intended deployment;
- duplicate/shadowed routes;
- package build failure;
- TypeScript client type-check failure;
- failed live PostgreSQL/Redis/Mongo CI job;
- source package containing real `.env` or runtime secrets;
- stale verification report claiming results that were not run.

## 3. Coverage policy

Aggregate branch-aware coverage has a project floor, but critical modules also have independent floors. This prevents tests in easy utility code from hiding low security/runtime coverage.

Current gate definitions live in `scripts/check_critical_coverage.py`, not in prose. CI executes that script from the generated coverage JSON.

## 4. Live-service distinction

Tests that need PostgreSQL, Redis, MongoDB or unavailable async drivers may be skipped in a constrained local sandbox. A skip is **not a pass**. Official CI provides service containers and runs the full test suite.

## 5. No fake adapters

A configuration enum must not advertise a backend that immediately raises “not implemented.” v0.4 therefore exposes only the implemented local media backend. Future object-storage adapters should become valid config only when a real implementation and tests exist.

## 6. Documentation as contract

Documentation drift is a bug for a declarative framework. A developer writes JSON based on docs; therefore stale field names, old merge semantics or nonexistent CLI switches are runtime hazards.

Release review includes searches for stale version metrics and broken local Markdown links.

## 7. Production-ready language

v0.4 is a hardening/alpha release. Passing the repository gates means the implemented contracts are substantially better tested; it does not prove every workload or infrastructure topology is safe.

Claims such as “financially exactly once,” “unlimited scale,” or “secure against arbitrary SQL” are explicitly avoided.

## 8. Evidence over endpoint counts

Useful release evidence includes:

- exact unit/component test count;
- exact local skipped integration count;
- branch-aware coverage;
- critical module floors;
- schema/doctor/OpenAPI checks;
- live-service CI result;
- package/container build result;
- reproducible checksum/manifest.

The number of generated endpoints is secondary.
