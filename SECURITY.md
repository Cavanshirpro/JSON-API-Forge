# Security policy

## Supported versions

| Version | Security support |
|---|---|
| 0.5.x | Current supported SDK line |
| 0.4.x | Superseded; upgrade recommended |
| 0.3.x and older | Historical |

Do not disclose exploits, tokens, credentials or private deployment data in a public issue. Prefer GitHub Private Vulnerability Reporting on the canonical repository. If it is unavailable, request a private contact channel without including exploit details.

Include the affected SDK version, Python/platform, impact, minimal reproduction and any known mitigation. No response-time SLA is promised.

Applications remain responsible for TLS trust, secret storage, narrow server-side roles, dependency updates and safe handling of downloaded files. The client rejects unsafe URLs and token formats, disables redirects/proxy inheritance/cookies, bounds bodies, snapshots uploads and atomically saves downloads, but it cannot compensate for a compromised server or host.
