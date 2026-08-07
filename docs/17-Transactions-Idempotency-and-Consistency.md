# Transactions, idempotency and consistency

This chapter matters for economies, payments, inventories, purchases, reward claims and any endpoint where a duplicate write is unacceptable.

## Database transaction

An RPC with `transaction:true` executes every configured SQL statement using one SQLAlchemy transaction. If validation, a row-count guard, SQL execution or a later statement fails, the transaction exits with rollback.

Example debit guard:

```sql
UPDATE economy_accounts
SET balance = balance - :amount
WHERE discord_user_id = :from_user
  AND balance >= :amount
```

with:

```json
{
  "require_rowcount_min":1,
  "require_rowcount_max":1
}
```

No preliminary `SELECT balance` is required. The condition and mutation happen atomically in the database, avoiding a classic read-then-write race.

## HTTP retry problem

Networks fail after a server commits but before the caller receives the response. The caller cannot know whether retrying is safe.

For `idempotency:true`, send:

```http
Idempotency-Key: discord:123456789012345678
```

Forge hashes that together with project, operation and principal. Before the SQL transaction begins, it inserts a unique `pending` reservation in the internal DB.

```text
request A ─┐
           ├─ unique claim → winner → SQL transaction → save response
request B ─┘                 loser  → pending/replay, never executes SQL
```

After completion, a retry receives the stored response with `_idempotent_replay:true` when the response is an object.

## Failure handling

If the winner fails before completion, Forge removes the pending reservation so a genuine retry can execute. If a process dies and leaves a reservation, `idempotency_pending_ttl_seconds` allows stale recovery.

For payment-grade systems, keep the internal Forge DB on a shared durable database rather than one SQLite file per independently running server.

## Cache ordering

A successful mutation invalidates configured resource/operation generations. Sensitive write RPCs should normally have operation cache disabled. Read RPCs such as balance lookups can have short TTLs; mutation invalidation prevents old generations from being reused.

## Stronger invariants

Use database constraints where possible: unique keys, foreign keys, CHECK constraints and appropriate isolation. JSON-level validation protects API inputs; database constraints protect stored truth.
