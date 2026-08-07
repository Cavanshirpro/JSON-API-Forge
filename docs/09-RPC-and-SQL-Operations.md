# Named RPC and SQL operations

`operations[]` is the bridge between “JSON-configured API” and transactional SQL. It gives a stable HTTP contract without giving callers a raw SQL console.

## Minimal operation

```json
{
  "name":"user.profile",
  "method":"GET",
  "database":"primary",
  "permission":"users.profile.read",
  "transaction":false,
  "statements":[
    {
      "sql":"SELECT id, username FROM users WHERE id = :id",
      "mode":"fetch_one",
      "params":{"id":"$query.id"},
      "result_name":"user"
    }
  ]
}
```

Default path is `rpc/<name>`, so this becomes `GET /api/<app>/v1/rpc/user.profile?id=...`.

## Parameter sources

Statement values can be literals or declarative references:

```text
$body.amount
$body.user.id
$param.page        # normalized value from parameters[]
$query.page
$path.user_id
$header.x-client-version
$principal.subject
$principal.tenant_id
$principal.kind
$request.id
```

A literal beginning with `$` can be written as `$$literal`.

Values are passed as bind parameters to SQLAlchemy `text()`; they are not string-concatenated into SQL.

## Statement modes

```text
execute    mutation / rowcount
fetch_one  first mapping row or null
fetch_all  bounded list
scalar     first scalar value
```

`fetch_all` has `max_rows` to prevent a misconfigured report from materializing an unbounded result set.

## Row-count invariants

```json
{
  "require_rowcount_min":1,
  "require_rowcount_max":1
}
```

turns “no row changed” or “too many rows changed” into HTTP 409, which also rolls back a transactional operation.

## Transaction boundary

`transaction:true` executes all statements using one DB transaction. This is the default for RPCs. Use `transaction:false` primarily for reads.

## Input validation

`input_schema` is JSON Schema Draft 2020-12:

```json
{
  "type":"object",
  "required":["amount"],
  "additionalProperties":false,
  "properties":{
    "amount":{"type":"integer","minimum":1,"maximum":1000000}
  }
}
```

Validation happens before SQL.

## Query/header/cookie/path parameters

`parameters[]` can declare type, required/default, enum, numeric min/max, string min/max and regex pattern. Forge validates these and inserts their declarations into OpenAPI.

## Idempotency

Set `idempotency:true` for retry-sensitive writes. The client must send the configured idempotency header (default `Idempotency-Key`). Forge obtains a unique internal reservation before side effects, making duplicate concurrent execution safe across workers that share the same internal database.

## Caching read RPCs

```json
{
  "cache":{
    "enabled":true,
    "ttl_seconds":5,
    "vary_by_principal":false
  }
}
```

Mutating operations can list `invalidate_resources` and `invalidate_operations`. Forge bumps generation counters rather than scanning Redis for every matching key.

Do not cache a side-effecting RPC.

## Background hooks

`background_hooks` invokes trusted Python after the response has been prepared. This is appropriate for lightweight non-critical tasks. It is not a durable job queue; payment settlement, transcoding or critical email delivery should use an external worker/queue architecture.

## DDL/admin SQL

DDL/administrative verbs are disabled by default. `allow_ddl:true` exists for controlled server-owned operations, but migrations are the better production tool. Never grant an untrusted client the ability to choose SQL text.
