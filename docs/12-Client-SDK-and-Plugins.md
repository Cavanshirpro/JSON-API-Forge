# Client SDKs, plugins and direct HTTP use

Forge is protocol-first. Any language that can send HTTPS can use it: Python, C++, Java/Kotlin, JavaScript/TypeScript, C#, Rust, Go, game engines and shell scripts.

## Python client

`clients/python/json_api_forge_client.py` contains a small async client around one pooled `httpx.AsyncClient`.

```python
api = ForgeClient("https://api.example.com/api/app1/v1", api_key)

items = await api.list("notes", limit=50)
row = await api.get("notes", 42)
created = await api.create("notes", {"title":"hello"})
result = await api.rpc("economy.transfer", payload, idempotency_key=interaction_id)
```

Do not construct a new HTTP client for every command/request; reuse connections.

## TypeScript reference client

`clients/typescript/src/index.ts` provides a strict `fetch()`-based reference client. It supports API-key or bearer authentication, generic requests, CRUD helpers, RPC/idempotency headers, timeout/abort behavior and Forge error/request-ID propagation.

```ts
const forge = new ForgeClient({
  baseUrl: "https://api.example.com/api/app1/v1",
  apiKey: process.env.FORGE_API_KEY,
});

await forge.rpc(
  "economy.transfer",
  { from_user: "1", to_user: "2", amount: 50 },
  `discord:${interactionId}`,
);
```

The reference client is part of the canonical source tree; it is not a separately maintained alternative Forge distribution.

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


## Client-side idempotency rule

An idempotency key identifies one logical mutation, not one network attempt. Reuse the same key **only** when retrying the same semantic request. v0.4 fingerprints the request and rejects reuse of the same key for a changed payload.

## Public clients and secrets

A downloaded desktop/mobile/game/browser client should be considered inspectable by its user. Do not rely on hiding a privileged static API key in such a binary. Use end-user JWT/session identity and server-side authorization for untrusted clients; reserve static API keys for trusted service/plugin/server environments where the secret can actually be protected.
