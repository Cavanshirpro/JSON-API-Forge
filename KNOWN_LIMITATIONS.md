# Known Limitations

JSON API Forge v0.4 is an **alpha hardening release**, not an unconditional production certification.

The most important limits are:

- feature packs are secure backend primitives, not complete social/messaging/game business logic;
- realtime is best-effort and not a durable queue/broker;
- SQL idempotency covers same-database transactional side effects, not cross-system exactly-once execution;
- the media backend implemented in v0.4 is local filesystem only;
- file-backed data sources are not a distributed multi-host database;
- HTTP egress validation is not a substitute for network-level egress controls;
- declarative SQL is trusted server configuration, not attacker-safe arbitrary SQL;
- memory cache/rate-limit/realtime backends are process-local;
- API-key auth caching trades a short bounded cross-worker revocation window for fewer internal-DB lookups;
- cPanel/Passenger compatibility is primarily for HTTP APIs, not native high-volume WebSocket workloads;
- declarative schema creation is not a complete production schema migration system;
- built-in audit is not an immutable compliance ledger.

See [docs/41-Known-Limits-and-Non-Goals.md](docs/41-Known-Limits-and-Non-Goals.md) for the detailed engineering rationale and mitigation guidance.
