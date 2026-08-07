# FastAPI features exposed through Forge JSON

Forge uses FastAPI as the runtime rather than hiding it. The goal is to expose common FastAPI/Starlette capabilities declaratively while keeping arbitrary executable code behind trusted Python hooks.

## Routing

SQL resources, Mongo resources, RPC operations, data sources, media and event channels generate path operations. Custom endpoints can select ordinary HTTP methods and metadata such as summary, description, tags, deprecation and schema visibility.

Each app gets filtered project documentation:

```text
/api/<app>/v1/_docs
/api/<app>/v1/_redoc
/api/<app>/v1/_openapi.json
```

The project OpenAPI document includes Forge API-key/Bearer security schemes so Swagger consumers can authorize without learning another client tool.

## Request bodies and validation

Resource create/update schemas and RPC/custom `input_schema` use JSON Schema Draft 2020-12.

Custom endpoint `input_mode`:

```text
json
form
text
bytes
none
```

Multipart/form parsing can produce normal values and `UploadFile` objects. Large/general media workloads should use the dedicated media subsystem.

## Query/header/cookie/path parameters

`parameters[]` supports:

```text
type: string | integer | number | boolean
required/default
enum
minimum/maximum
min_length/max_length
pattern
```

Forge validates them and also exposes them in OpenAPI. Trusted hooks can read normalized values from `request.state.validated_parameters`.

## Dependency injection

Define trusted dependencies once:

```json
{
  "dependencies":[
    {
      "name":"signed-client",
      "callable":"app.App1.hooks.security:require_signed_client",
      "use_cache":true
    }
  ]
}
```

Then attach `"dependencies":["signed-client"]` to supported endpoints/resources. Forge creates normal FastAPI `Depends(...)` objects.

This is intentionally a trusted-code feature: an attacker must never be able to change the import path.

## BackgroundTasks

RPC/custom endpoints can configure `background_hooks`. Forge places them in FastAPI/Starlette `BackgroundTasks`, useful for small non-critical after-response work.

It is not a distributed/durable queue. CPU-heavy image/video work, critical notifications and payment workflows belong in a worker system (Celery/TaskIQ/Arq/etc.) behind a trusted hook/integration.

## Response types

A custom endpoint `response.kind` can choose:

```text
json     ORJSONResponse
text     PlainTextResponse
html     HTMLResponse
redirect RedirectResponse
stream   StreamingResponse
file     FileResponse
empty    Response
```

Status, media type, fixed headers and filename can also be declared.

## UploadFile/media

The media subsystem receives FastAPI `UploadFile` and streams chunks to storage rather than intentionally calling `await file.read()` for one giant in-memory allocation. It adds size/MIME/extension policy, metadata, dedupe, quotas and signed read URLs.

## WebSocket

`event_channels[].websocket_enabled:true` creates:

```text
/api/<app>/v1/<channel path>/ws
```

With Redis realtime backend, published events can cross Forge workers/servers.

## Server-Sent Events

`event_channels[].sse_enabled:true` creates a `StreamingResponse` using `text/event-stream` and heartbeat behavior. SSE is useful for one-way notification/feed delivery when full duplex WebSocket is unnecessary.

## Lifespan

FastAPI lifespan initializes and closes process resources cleanly: internal DB, SQL pools, Mongo clients, cache, rate limiter, audit writer, data-source HTTP client, realtime hub and media backend.

## Middleware

Forge uses middleware for request IDs, project-aware CORS, HTTPS/IP/body protection, concurrency backpressure, timeout, security headers, audit timing, GZip and Trusted Host checks.

Middleware is deliberately runtime-owned rather than allowing arbitrary user-supplied middleware classes from writable JSON.

## OpenAPI webhooks

`webhook_docs` uses FastAPI's OpenAPI webhook feature to describe events your API can send. This is documentation of the contract; it does not pretend to be a durable outbound webhook delivery queue.

## OpenAPI extra metadata

Custom endpoints can supply `openapi_extra`, and RPC request schemas/parameter declarations are injected into generated route metadata.

## Security model

Forge authentication is implemented in the runtime so generated endpoint types share one principal model. Project OpenAPI advertises API-key/Bearer schemes; runtime permission checks remain authoritative.

## Why not make every Python object name configurable?

FastAPI can technically accept arbitrary dependencies, middleware, response classes and callables. Turning every import path/class constructor into remotely editable JSON would turn configuration into code execution.

Forge therefore uses this rule:

```text
safe/repetitive behavior → JSON DSL
arbitrary behavior       → trusted Python extension
```

That boundary keeps the framework flexible without pretending that code itself can always be safely reduced to data.
