# Outbound HTTP and Egress Security

HTTP data sources turn Forge into an API gateway/proxy for selected upstream services. That means upstream URLs become part of the server's egress trust boundary.

## 1. Secure defaults

A data source uses a configured URL and supports bounded timeout/retry/response behavior. By default:

- plain HTTP is rejected unless explicitly allowed;
- private/link-local targets are rejected unless explicitly allowed;
- redirects are not automatically followed by the resilient client;
- response bytes are bounded while streaming;
- non-idempotent POST/PATCH retries are not automatically enabled.

## 2. Example

```json
{
  "name": "weather",
  "type": "http",
  "path": "external/weather",
  "url": "https://provider.example/api/weather",
  "public": false,
  "read_permission": "weather.read",
  "timeout_seconds": 5,
  "max_response_bytes": 1048576,
  "retries": 2,
  "forward_query": true
}
```

Secrets can be supplied from server-side environment references in configured headers. They are not returned to the client.

## 3. SSRF guardrails are not a firewall

Application-level URL/DNS validation reduces obvious SSRF risks but cannot provide the guarantees of network isolation. DNS can change, infrastructure has special metadata endpoints, and proxies can alter routing.

For sensitive environments, enforce egress at the network/container/VPC/firewall layer as well.

## 4. Private network opt-in

`allow_private_networks:true` is a powerful exception. Production doctor surfaces it as a warning because the upstream may now reach internal services.

## 5. Plain HTTP opt-in

`allow_insecure_http:true` permits plaintext egress and is also surfaced by production diagnostics.

## 6. Redirects

Automatic redirects are disabled in the resilient HTTP client. This avoids validating one destination and silently following to a different trust domain.

## 7. Retry policy

Retries are safe by default only for methods treated as idempotent by the client policy. A POST/PATCH can be replayed only when the configuration explicitly opts in and the upstream API has its own idempotency semantics.

## 8. Circuit breaker

Repeated transient transport/retryable failures can open a per-upstream circuit for a cooldown period. The breaker is a worker-local resilience tool; it is not a distributed health coordinator.

## 9. Bounded response buffering

The client checks declared `Content-Length` when available and also counts streamed bytes. An upstream cannot bypass the limit simply by omitting `Content-Length`.

## 10. Forwarded client input

`forward_query` and `forward_body` are explicit decisions. Do not forward arbitrary client values to privileged internal services without validating the upstream contract.

## 11. Secret logging

Do not log configured Authorization/API secrets. Treat upstream error bodies as untrusted data and avoid exposing internal topology to public clients.
