# Outbound HTTP and Egress Security

Outbound HTTP is a server/operator capability. Destination rules, HTTP-vs-HTTPS policy, private-network access and mutation retries must be reviewed as security configuration.

The resilient client disables redirects and can enforce maximum response bytes while streaming. Permanent 4xx responses are not retried. GET/HEAD/OPTIONS/PUT/DELETE can use bounded retries; POST/PATCH retries require explicit opt-in because retrying a mutation without upstream idempotency can duplicate effects.

Application checks do not replace firewall, VPC, proxy or DNS egress controls. Restrict infrastructure access to metadata endpoints, internal admin services and private networks unless explicitly needed.
