# Data sources and API gateway

A data source turns server-owned non-SQL data into a normal Forge endpoint. In v0.4 it is private by default: configure a read permission or explicitly set `public:true`.

Supported types:

```text
json_file
yaml_file
csv_file
static
http
```

## “I already have a JSON file; can requests come to my server?”

Yes. Put the file below the app directory and declare it:

```text
app/App1/
├── config/80-content.json
└── data/catalog.json
```

```json
{
  "data_sources":[
    {
      "name":"catalog",
      "path":"content/catalog",
      "type":"json_file",
      "file":"data/catalog.json",
      "read_permission":"catalog.read",
      "write_permission":"catalog.write",
      "writable":true,
      "id_field":"id",
      "cache_ttl_seconds":30
    }
  ]
}
```

Now callers hit **your server**:

```http
GET /api/app1/v1/content/catalog?category=tools&limit=20
X-API-Key: ...
```

and Forge reads the file and returns the response.

If writable and a write permission is configured, it also generates:

```text
POST   /content/catalog
PATCH  /content/catalog/{id}
PUT    /content/catalog/{id}
DELETE /content/catalog/{id}
```

Writes use both a per-process async lock and a cross-process file lock, then temporary-file replacement. This protects same-host workers from read/modify/write collisions. JSON/YAML is still suitable for small configuration/content datasets, not thousands of transactional writes; use PostgreSQL/MongoDB for that.

CSV is read-only in this build.

## Static configuration endpoint

```json
{
  "name":"client-config",
  "type":"static",
  "path":"config/client",
  "data":{"minimum_version":"2.3.0","maintenance":false}
}
```

This is useful for feature flags or public client metadata that changes only on deployment.

## HTTP gateway/proxy

A source can represent a fixed external service:

```json
{
  "name":"weather",
  "type":"http",
  "path":"external/weather",
  "url":"https://api.example.com/weather",
  "method":"GET",
  "headers":{"Authorization":"$env:UPSTREAM_TOKEN"},
  "forward_query":true,
  "cache_ttl_seconds":30,
  "timeout_seconds":5,
  "retries":2
}
```

Flow:

```text
mobile/plugin → YOUR Forge endpoint → external API
                               ↑ server-owned token
```

The external credential never reaches the client.

The outbound HTTP layer reuses connections and includes timeout, retry/backoff and circuit-breaker behavior. Redirect following is not needed for JWKS and data-source targets should be fixed by trusted config rather than supplied by the caller, reducing SSRF exposure.

## Choosing a backend

Use SQL for relational transactions and strong constraints. Use MongoDB for document-shaped mutable data. Use JSON/YAML for small server-owned content/configuration. Use `http` when Forge is an authenticated/cached gateway to another service. Use a trusted custom hook when transformation/business logic is too complex for these declarative primitives.


## v0.4 public-read / public-write split

`public:true` affects **reads only**. This prevents a developer from making a catalog readable without realizing that POST/PATCH/DELETE became anonymous too.

Public read + protected mutation:

```json
{
  "name":"catalog",
  "type":"json_file",
  "file":"data/catalog.json",
  "public":true,
  "writable":true,
  "write_permission":"catalog.write"
}
```

Deliberately public mutation requires the separate opt-in:

```json
{
  "public":true,
  "public_write":true,
  "writable":true
}
```

Use `public_write` only when anonymous mutation is genuinely part of the product.

## Filesystem safety and scaling limit

Local file sources resolve inside the project directory and reject path escape. Writable JSON/YAML uses async locking, cross-process file locking and atomic replacement on the same host. This is a useful small-data mechanism, not a distributed database protocol. A shared/NFS filesystem can have different locking/atomicity behavior; high-write authoritative state belongs in PostgreSQL/MongoDB.


## Retry safety for outbound HTTP sources

`retries` is a resilience budget, not permission to repeat arbitrary side effects. v0.4 applies conservative retry semantics:

- `GET`, `HEAD`, `OPTIONS`, `PUT` and `DELETE` may use the configured retry budget;
- `POST` and `PATCH` are attempted once by default, even if `retries` is greater than zero;
- only transport/timeouts and transient statuses such as `408`, `425`, `429`, `500`, `502`, `503` and `504` are retryable;
- ordinary semantic/client failures such as `400`, `401`, `403` and `404` are not retried and do not trip the transient circuit breaker;
- redirects are not followed automatically.

If an upstream provides a real idempotency contract and you intentionally want mutation retries, set:

```json
{
  "type": "http",
  "method": "POST",
  "retries": 2,
  "retry_non_idempotent": true
}
```

Do this only when the upstream request itself carries a stable provider idempotency key or is otherwise safe to repeat. JSON API Forge cannot infer whether a third-party POST charges a card, creates an order or sends a message.
