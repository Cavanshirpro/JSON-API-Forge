# Data sources and API gateway

A data source turns server-owned non-SQL data into a normal Forge endpoint.

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

If writable, it also generates:

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
