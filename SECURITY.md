# Security policy

## Supported versions

| Version | Security support |
|---|---|
| 0.5.x | Current supported example line |
| 0.4.x | Superseded; upgrade recommended |
| 0.3.x and older | Historical |

Do not publish exploit details, credentials, private keys, real customer data or private deployment information in a public issue. Prefer GitHub Private Vulnerability Reporting on the canonical repository.

These projects are reference/development configurations, not ready-made production security policies. Generate fresh secrets with `forge init`, preserve private-by-default routes, use narrow roles, validate with the matching v0.5.0 `main`, and run `forge doctor --production` after supplying deployment-specific TLS, hosts, CORS, database, Redis and proxy settings. Never reuse example or CI data as real records.
