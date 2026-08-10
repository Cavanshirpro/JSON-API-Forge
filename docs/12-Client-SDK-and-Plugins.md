# Client SDK and Plugins

`clients/python/json_api_forge_client.py` and `clients/typescript/` are reference clients, not separately distributed alternative framework editions. They demonstrate narrow API-key use, RPC calls, CRUD access, timeouts and idempotency headers.

Keep privileged API keys on trusted server-side clients. Browser/mobile environments that cannot protect static credentials should normally authenticate users with short-lived identity tokens and expose only the permissions needed by that client.

The TypeScript reference is checked in CI against Node 22 / TypeScript 7.0.2. The Python client uses `httpx.AsyncClient` pooling and supports async context management.
