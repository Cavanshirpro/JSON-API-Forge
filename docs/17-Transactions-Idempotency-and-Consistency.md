# Transactions, idempotency and consistency

This chapter matters for economies, purchases, inventory, reward claims, order creation and any endpoint where a duplicate write has a real cost.

## 1. SQL transaction boundary

An operation with:

```json
{
  "transaction": true
}
```

executes all configured SQL statements on one SQLAlchemy connection/transaction for its selected database alias.

If validation, SQL execution, a row-count invariant or later statement fails, the transaction rolls back.

Example debit:

```sql
UPDATE economy_accounts
SET balance = balance - :amount
WHERE discord_user_id = :from_user
  AND balance >= :amount
```

with:

```json
{
  "require_rowcount_min": 1,
  "require_rowcount_max": 1
}
```

The balance condition is part of the atomic update. A separate read-before-write balance check is not required for this invariant.

## 2. Why network retry is dangerous

A request can produce this timeline:

```text
client -> server
server -> database COMMIT
network response lost
client times out
```

The client does not know whether the write committed. Blindly repeating a non-idempotent transfer can perform it twice.

## 3. v0.4 idempotency model

For an operation configured with:

```json
{
  "transaction": true,
  "idempotency": true
}
```

the client sends:

```http
Idempotency-Key: discord:123456789012345678
```

Forge derives two concepts:

1. **logical idempotency identity** — project + operation + principal + raw idempotency key;
2. **request fingerprint** — canonical hash of the HTTP method, body, path parameters, complete query multiset, validated declarative parameters, tenant context, and only the request headers that the operation actually references.

The idempotency row lives in the selected **business database**, beside the operation side effects.

Conceptual transaction:

```text
BEGIN
  claim idempotency logical key + request fingerprint
  run debit
  run credit
  insert ledger row
  persist operation response as completed idempotency result
COMMIT
```

This matters because the business mutation and completed replay record succeed or fail together.

## 4. Same key, same request

First request executes normally and commits.

A later retry with the same logical key and the same fingerprint reads the persisted response rather than performing the SQL side effects again.

Forge does not mutate the application JSON payload to expose replay state. A replay is reported out-of-band with:

```http
X-Forge-Idempotent-Replay: true
```

This keeps framework telemetry from colliding with user-owned response fields.

## 5. Same key, different request

This is rejected.

Example:

```text
key=discord:123 amount=10  -> succeeds
key=discord:123 amount=100 -> conflict
```

Without request fingerprinting, the second request could incorrectly receive the first result or cause ambiguous behavior. v0.4 treats key reuse for a different logical request as a client error.

## 6. Concurrent duplicate request

If two workers try the same logical key concurrently, the unique idempotency record serializes ownership. The loser observes the existing completed/pending state rather than independently executing the side effects.

A temporary pending conflict should be retried with the **same request and same key** using bounded backoff, not a newly generated key.


## 7. Retention and ledger growth

`idempotency_ttl_seconds` is both a replay window and a retention boundary. v0.4 keeps exact same-key reuse semantics by removing an expired row for that key before a new claim. It also runs a throttled opportunistic janitor for each `(project, operation)` so callers that always generate new keys do not make the ledger grow forever.

The ledger includes an index over:

```text
project_slug + operation_name + updated_at
```

Cleanup first selects at most `idempotency_cleanup_batch_size` expired IDs through that index and deletes only that bounded batch. It is intentionally not performed on every hot-path request; when a full batch indicates backlog, the next cleanup becomes eligible quickly under active traffic. Operators should still monitor database growth, size `idempotency_ttl_seconds` for the real retry horizon, and tune `idempotency_cleanup_batch_size` for their write rate and database capacity.

## 8. Crash semantics

### Crash before COMMIT

Database transaction rolls back:

```text
business side effects: rolled back
idempotency result:    rolled back
```

Retry can execute normally.

### Crash after COMMIT

Both business state and completed idempotency result are committed together. Retry replays.

This is the key v0.4 improvement over a split internal-DB completion design.

## 9. What this guarantee does not cover

One SQL database transaction cannot atomically cover independent systems such as:

- Stripe/payment provider;
- Discord API;
- SMTP/email;
- S3/object storage;
- a second PostgreSQL database;
- MongoDB;
- another microservice.

Example unsafe assumption:

```text
PostgreSQL COMMIT
then external payment call
```

or:

```text
external payment succeeds
then PostgreSQL crashes
```

Forge cannot roll the external provider backward through SQLAlchemy.

For these cases use one or more of:

- provider idempotency keys;
- transactional outbox;
- inbox/deduplication table;
- durable job queue;
- workflow/saga compensation;
- reconciliation process.

## 10. Outbox pattern

A robust pattern is:

```text
BEGIN SQL TRANSACTION
  update business state
  insert outbox event
  persist Forge idempotency result
COMMIT

separate worker:
  read unsent outbox event
  call external provider with stable provider idempotency key
  mark sent / retry with backoff
```

The database transaction guarantees that business state and the intent to perform the external action are recorded together.

## 11. Isolation and constraints

Idempotency does not replace database invariants.

Use:

- unique constraints;
- foreign keys;
- CHECK constraints;
- conditional updates;
- suitable transaction isolation;
- row/version locking where domain semantics require it.

Examples:

```sql
CHECK (balance >= 0)
UNIQUE (provider_event_id)
UNIQUE (order_number)
```

A JSON request schema validates API shape; database constraints protect stored truth against every code path.

## 12. Cache ordering

A successful write may invalidate resource/operation cache generations after the operation completes. Side-effecting idempotent operations cannot enable response cache; the idempotency ledger is their replay mechanism.

For correctness-sensitive reads such as balance:

- avoid stale windows unless explicitly acceptable;
- invalidate relevant cache namespace after successful mutation;
- remember that cross-service replicas/caches may have their own consistency delay.

## 13. Client rules

A client should:

1. generate one logical idempotency key for the intended action;
2. reuse it for network retries of **that same action**;
3. keep the payload semantically identical;
4. treat a changed-request conflict as a bug, not a transient failure;
5. use exponential backoff/jitter for transient pending/service failures;
6. not create a new key merely because the response timed out.

Discord interaction IDs and payment-provider event IDs are often natural logical keys.

## 14. Testing checklist

For every money/order/inventory operation test:

- insufficient balance -> no debit/credit/ledger partial state;
- successful request -> exactly one state transition;
- duplicate same key/request -> replay, no second side effect;
- same key/different amount -> conflict;
- statement failure -> complete rollback;
- concurrent duplicate -> one logical execution;
- process termination behavior in a staging/real DB setup;
- cache invalidation after commit;
- tenant/user authorization before any sensitive mutation.

## 15. Terminology

Prefer precise statements:

- **“transactionally idempotent within one configured SQL database”** — accurate for the v0.4 operation design;
- **“exactly once everywhere”** — not a valid claim for a distributed system without additional protocols/architecture.
