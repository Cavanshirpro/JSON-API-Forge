# Generated endpoint map

Exact paths depend on `api_prefix` and each configured `path`.

## System

```text
GET /health
GET /ready
GET /metrics                         when metrics enabled
GET <prefix>/meta
GET <prefix>/_docs                   per-project Swagger
GET <prefix>/_redoc
GET <prefix>/_openapi.json
```

## API-key administration

```text
POST   <prefix>/admin/api-keys
GET    <prefix>/admin/api-keys
DELETE <prefix>/admin/api-keys/{key_id}
POST   <prefix>/admin/jwt            local_hs256 mode only
```

## SQL resources

Depending on `allowed_actions`/settings:

```text
GET    <prefix>/<resource>
GET    <prefix>/<resource>/_count
GET    <prefix>/<resource>/{item_id}
POST   <prefix>/<resource>
POST   <prefix>/<resource>/_batch
PATCH  <prefix>/<resource>/{item_id}
PUT    <prefix>/<resource>/{item_id}
DELETE <prefix>/<resource>/{item_id}
```

## Mongo resources

```text
GET/POST <prefix>/<resource>
GET      <prefix>/<resource>/_count
GET/PATCH/PUT/DELETE <prefix>/<resource>/{item_id}
```

subject to configured actions.

## RPC

```text
<METHOD> <prefix>/<operation.path>
```

Default operation path is `rpc/<operation.name>`.

## Data sources

Read/fixed HTTP method at:

```text
<METHOD> <prefix>/<source.path>
```

Writable JSON/YAML adds POST on collection and PATCH/PUT/DELETE on `/{item_id}`.

## Event channels

```text
POST <prefix>/<channel.path>          publish
GET  <prefix>/<channel.path>/stream   SSE
WS   <prefix>/<channel.path>/ws       WebSocket
```

## Media

```text
POST   <prefix>/media
POST   <prefix>/media/_batch
GET    <prefix>/media/{id}
GET    <prefix>/media/{id}/meta
POST   <prefix>/media/{id}/signed-url
DELETE <prefix>/media/{id}
```

## Custom endpoints

Exactly the configured method/path.

Use `python forge.py routes` to print the real route map for the current app folders.
