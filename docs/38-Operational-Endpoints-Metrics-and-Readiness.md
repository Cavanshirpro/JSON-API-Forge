# Operational Endpoints, Metrics, and Readiness

Process-wide operations require a different trust boundary from per-project application APIs.

## 1. `/health`

`/health` is a minimal liveness signal. It answers whether the process can serve the liveness endpoint without publishing detailed database/cache topology.

It is suitable for basic process health checks.

## 2. `/ready`

`/ready` checks configured runtime dependencies. The public/default representation is redacted: a load balancer needs a readiness decision, not connection strings or detailed internal failure context.

Detailed operator diagnostics require operator authorization.

## 3. `/metrics`

Prometheus metrics are process-wide. In a multi-project runtime they can expose information about several applications, so application API keys are not automatically operator credentials.

When metrics are enabled, production requires a strong separate:

```env
OPERATOR_TOKEN=...
```

## 4. Why separate operator trust

Consider:

```text
App1 admin API key -> App1 application administration
Operator token      -> process-wide telemetry for App1 + App2 + runtime
```

These are not equivalent scopes.

## 5. Audit observability

The audit writer uses a bounded asynchronous queue and batch writes so audit persistence does not block every API response. Queue overflow/write failure must be observable through logs/metrics/counters.

The built-in audit path is not an immutable compliance ledger. Compliance workloads may require external append-only/retained logging.

## 6. Cache/rate-limit observability

Production monitoring should include:

- cache hit/miss/stale/failure state;
- Redis availability;
- rate-limit rejection counts;
- overload/concurrency rejection counts;
- audit queue drops/write failures;
- realtime queue overflow/disconnects;
- outbound HTTP circuit/failure counts;
- request latency/error rates.

## 7. Readiness and migrations

A process configured for schema `validate` mode should fail readiness/startup when required support schema is absent. Run `forge migrate` before shifting traffic.

## 8. Monitoring token handling

Do not place the operator token in public frontend code. Monitoring/health automation should send it from trusted infrastructure where detailed telemetry is required.
