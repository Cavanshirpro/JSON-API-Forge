# Reverse Proxy Trust, TLS, and Client IP

Reverse-proxy handling is a security boundary because client IP affects IP allow/deny policies, pre-auth rate limiting, audit context and HTTPS enforcement.

## 1. Why Forge does not blindly trust forwarding headers

Headers such as:

- `X-Forwarded-For`;
- `X-Forwarded-Proto`;
- `X-Forwarded-Host`;

are ordinary client-controlled HTTP headers unless the immediate network peer is a trusted reverse proxy.

Forge therefore interprets proxy headers only when the direct peer falls inside an explicitly configured trusted proxy CIDR.

```json
{
  "protection": {
    "trusted_proxy_cidrs": ["127.0.0.1/32", "10.10.0.0/16"]
  }
}
```

## 2. Official Uvicorn launch behavior

The official Forge launch paths intentionally disable Uvicorn's automatic proxy-header rewriting. Forge needs to see the direct peer before deciding whether forwarded values are trustworthy.

Do not independently enable proxy-header rewriting unless you fully understand how it interacts with Forge's trust model.

## 3. Client IP resolution

Conceptually:

```text
Internet client -> trusted edge -> trusted reverse proxy -> Forge
```

Forge starts with the direct peer and walks forwarded information only inside the configured trust boundary. A direct untrusted client cannot simply send `X-Forwarded-For: 127.0.0.1` and become localhost.

## 4. HTTPS enforcement

A project can enable:

```json
{
  "security": {
    "require_https": true
  }
}
```

When TLS terminates at a trusted reverse proxy, Forge may use trusted forwarded protocol information. From an untrusted peer, that header is ignored.

## 5. Host isolation

Each project has its own `trusted_hosts`. This is enforced project-by-project rather than by only combining every project's hosts into one global list.

This matters in multi-project deployments:

```text
api-bot.example.com   -> /api/bot/v1
api-game.example.com  -> /api/game/v1
```

A host accepted for the bot project must not automatically satisfy the game project's host policy.

## 6. Non-overlapping API prefixes

Project API prefixes may not overlap at path boundaries. For example these are rejected together:

```text
/api/app
/api/app/admin
```

This avoids disagreement between middleware project selection and router matching.

## 7. cPanel / Passenger

Passenger compatibility uses the WSGI bridge and is primarily intended for ordinary HTTP API use. Native WebSocket/high-concurrency realtime workloads are better deployed as ASGI directly behind a proxy that supports long-lived connections.

See `cPanelGuide.md` for the deployment steps and limitations.

## 8. Recommended production topology

```text
Internet
   |
Cloud/WAF/CDN (optional)
   |
Nginx/Caddy/managed LB
   |
Uvicorn / JSON API Forge
   |
PostgreSQL + Redis + optional MongoDB
```

Only place addresses/ranges you control in `trusted_proxy_cidrs`.

## 9. Failure checklist

Before production verify:

- direct Forge port is not unintentionally public;
- trusted proxy CIDRs are exact enough;
- TLS termination sends protocol headers only from trusted infrastructure;
- `security.require_https` matches deployment topology;
- each project's host allowlist is correct;
- pre-auth rate limiting sees expected client identities;
- audit logs do not rely on spoofable IP information.
