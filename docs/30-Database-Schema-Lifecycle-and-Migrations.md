# Database Schema Lifecycle and Migrations

JSON API Forge can create small framework-owned support schemas, but production deployments should not confuse convenient development-time DDL with a complete application migration strategy.

## 1. Two classes of schema

### Forge-owned support tables

Forge uses internal/support tables for capabilities such as:

- API-key metadata;
- one-time bootstrap state;
- audit metadata;
- media metadata and owner usage accounting;
- operation idempotency ledgers in application databases.

### Application-owned tables

Resources with `auto_create:true` can create declaratively defined tables. This is convenient for development, examples, and small deployments, but it is not a general replacement for carefully reviewed destructive/transformational migrations.

## 2. `support_schema_mode`

Each SQL database has:

```json
{
  "support_schema_mode": "create"
}
```

or:

```json
{
  "support_schema_mode": "validate"
}
```

### `create`

The runtime may create required Forge support tables and declarative `auto_create` tables. This is the developer-friendly mode.

### `validate`

The runtime verifies that required support structures exist instead of performing normal startup DDL. Use this after an explicit deployment migration in production.

## 3. Internal schema mode

The framework-internal metadata database follows the same principle through:

```env
INTERNAL_SCHEMA_MODE=validate
```

For production, the intended flow is:

```bash
forge migrate
forge doctor --production
# deploy/restart runtime configured for validate mode
```

## 4. `forge migrate`

`forge migrate` explicitly initializes:

1. the internal Forge metadata schema;
2. required operation-idempotency support schema for configured SQL databases;
3. declarative auto-create resource tables where applicable.

It is designed to move schema creation out of the request-serving startup path.

## 5. What `forge migrate` is not

It is not a full schema-diff engine. It does not promise to safely infer transformations such as:

- rename a populated column;
- split one table into two;
- backfill a new non-null field;
- change data type with custom conversion;
- rebuild large indexes online;
- coordinate zero-downtime application migrations;
- rollback arbitrary business-schema changes.

For complex production schema evolution, use an explicit migration workflow appropriate to your database and version the migration with the application configuration.

## 6. v0.4 idempotency schema

Atomic SQL-operation idempotency uses `_forge_v4_operation_idempotency` in the same application database as the protected side effects. This placement is intentional: the idempotency result and business mutation can commit in the same database transaction.

The v0.4 ledger also carries a retention index over project, operation and update time so TTL cleanup does not require an unindexed full-table scan.

Older installations may still contain the v0.3 internal `_forge_v3_idempotency` table. v0.4 does **not** automatically perform a destructive `DROP` of legacy metadata. After an operator confirms it is unused and backups are valid, cleanup can be performed as a separate controlled maintenance action.

## 7. Deployment sequence

A conservative production deployment is:

```text
1. Back up database / verify restore path.
2. Deploy configuration/code to a staging target.
3. Run forge validate.
4. Run forge doctor --production.
5. Run forge migrate against the target database.
6. Run application-specific migrations/backfills if any.
7. Start Forge in validate mode.
8. Check /health and authenticated /ready details.
9. Run smoke/API contract tests.
10. Shift traffic.
```

## 8. Multi-project deployments

Each app can point to different SQL aliases and engines. Migration therefore operates project-by-project. A failure in one project must not be treated as evidence that every other project's database was successfully prepared.

Keep migration logs and database backups per environment.

## 9. Pool configuration

Application databases expose pool settings such as:

```json
{
  "pool_pre_ping": true,
  "pool_size": 20,
  "max_overflow": 40,
  "pool_timeout": 10,
  "pool_recycle": 1800
}
```

The internal metadata database has separate environment-level pool settings. High API-key/audit/media traffic can bottleneck on the internal database even when application databases have large pools; size both based on measurements.

## 10. SQLite

SQLite is useful for development and small single-node deployments. `forge doctor --production` warns on SQLite because concurrency, durability, backup and multi-worker expectations must be evaluated explicitly.

## 11. Release rule

Never advertise a migration as safe merely because `create_all()` succeeds on an empty database. Production migration confidence requires representative data, backups, restore testing, and the exact upgrade path being rehearsed.
