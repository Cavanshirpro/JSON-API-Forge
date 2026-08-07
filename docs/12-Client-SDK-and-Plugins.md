# Client SDKs, plugins and direct HTTP use

Forge is protocol-first. Any language that can send HTTPS can use it: Python, C++, Java/Kotlin, JavaScript/TypeScript, C#, Rust, Go, game engines and shell scripts.

## Python client

`clients/python/json_api_forge_client.py` contains a small async client around one pooled `httpx.AsyncClient`.

```python
api = ForgeClient("https://api.example.com/api/app1/v1", api_key)

items = await api.list("notes", params={"limit":50})
row = await api.get("notes", 42)
created = await api.create("notes", {"title":"hello"})
result = await api.rpc("economy.transfer", payload, idempotency_key=interaction_id)
```

Do not construct a new HTTP client for every command/request; reuse connections.

## Plugin key model

Give every third-party integration its own key. Example:

```text
Official mobile backend key → high budget, selected server permissions
Discord economy bot key     → economy balance/transfer only
Read-only plugin key         → notes.read / leaderboard.list
Admin automation key        → narrowly selected admin operation
```

This enables independent revocation, limits and audit identity.

## C++ outline

A C++ plugin does not need PostgreSQL libraries if it uses Forge. It only needs an HTTPS client such as libcurl/cpr/QtNetwork:

```text
POST https://host/api/app1/v1/rpc/economy.transfer
X-API-Key: ...
Content-Type: application/json
Idempotency-Key: ...
```

Body:

```json
{"from_user":"1","to_user":"2","amount":50}
```

Forge owns the SQL transaction.

## Java/Kotlin outline

Use Java `HttpClient`, OkHttp or Ktor client. Keep the API key in a trusted server/plugin environment. Never embed a privileged key in a public Android APK; end-user apps should normally authenticate with user JWTs and receive user-level permissions.

## Browser/web client

Use bearer JWT authentication rather than a reusable privileged API key because browser JavaScript is inspectable. Configure exact production CORS origins.

## Retries

GET/read calls may generally be retried. Mutation retries require semantic care. For operations marked `idempotency:true`, reuse the same logical idempotency key. Do not generate a new key on every retry.

## Generated OpenAPI as SDK source

Each app exposes `_openapi.json`. You can feed this into standard OpenAPI client generators if you want strongly typed SDKs in another language. Custom handwritten clients remain useful when you want domain methods such as `transfer()` instead of raw endpoint names.
