# Realtime Delivery and Backpressure

JSON API Forge realtime channels provide lightweight WebSocket/SSE fan-out. They are intentionally **best-effort realtime transport**, not a durable message broker.

## 1. Backends

```json
{
  "realtime": {
    "backend": "memory"
  }
}
```

is process-local.

```json
{
  "realtime": {
    "backend": "redis"
  }
}
```

uses Redis pub/sub to fan events across workers.

Redis pub/sub is still not durable queue storage: an offline subscriber does not receive a persisted history from Forge.

## 2. Channel policy

Example:

```json
{
  "name": "notifications",
  "subscribe_permission": "notifications.subscribe",
  "publish_permission": "notifications.publish",
  "websocket_enabled": true,
  "sse_enabled": true,
  "max_message_bytes": 65536,
  "queue_size": 256,
  "max_websocket_connections": 1000,
  "max_sse_connections": 1000
}
```

Public publishing/subscribing requires explicit flags.

## 3. Slow-client isolation

Publishers do not synchronously wait for every WebSocket network send. Each socket has a bounded outbound queue and sender task. This prevents one slow client from serially delaying all other recipients.

If a queue is full, delivery is best-effort and overflow is observable. Do not interpret a publish response as durable per-recipient acknowledgement.

## 4. Connection ceilings

HTTP concurrency limits do not naturally bound long-lived streams after their response is established. Channels therefore have explicit per-worker WebSocket and SSE connection ceilings.

These values are per process. Capacity planning must multiply by worker count while considering file descriptors and memory.

## 5. Message rate limiting

WebSocket authentication happens at connection establishment, and v0.4 can additionally rate-limit messages inside an established socket. This closes the common loophole where one authenticated connection sends unlimited messages after passing a single handshake check.

## 6. Message-size limits

`max_message_bytes` is an application-level WebSocket message limit. It is checked after the ASGI server has delivered a text frame to the application, so it is **not** a substitute for the transport/server's own maximum WebSocket frame/message size. Configure Uvicorn/reverse-proxy limits as an outer bound for untrusted internet traffic. The channel limit remains useful as the per-application contract inside that transport boundary.

The WebSocket limit is independent from ordinary HTTP body policy.

## 7. Origin, host and browser credential policy

WebSocket routes apply project host/IP/TLS policy. Browser origins can be restricted through channel `allowed_origins`. API keys in WebSocket query strings are disabled by default because URLs often appear in proxy/browser logs.

Native/bot/desktop clients should prefer authentication headers. Browser WebSocket APIs cannot set arbitrary HTTP headers during the upgrade, so a private browser channel needs an explicitly designed credential path. v0.4 can opt in to query-string API-key fallback with `allow_websocket_query_api_key`, but production doctor warns about the leakage risk. Prefer a narrowly scoped/short-lived delegated credential when that fallback is necessary; do not place a long-lived root key in a browser URL.

## 8. Redis listener readiness

A Redis-backed event hub waits for its subscription listener to become ready before treating the channel as available. Listener startup failure is surfaced promptly rather than silently losing the first publish.

## 9. When to use a real broker

Use Kafka, NATS, RabbitMQ, Redis Streams, a managed queue, or another durable architecture when you need:

- acknowledged delivery;
- replay/history;
- consumer offsets;
- durable offline delivery;
- exactly-once/at-least-once processing policy;
- large fan-out independent of API workers.

Forge realtime is for API-adjacent live updates, not for replacing a durable event platform.
