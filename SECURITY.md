# Editor security policy

## Supported version

| Version | Security support |
|---|---|
| 0.5.x | Current supported Editor line |
| 0.4.x | Superseded; upgrade recommended |

Report vulnerabilities through GitHub Private Vulnerability Reporting on the
canonical repository. Do not place exploit details, session/setup tokens,
passwords, private project data or server configuration in a public issue.

The Editor keeps passwords, founder setup tokens and bearer sessions in
memory. It rejects redirects, ambient HTTP proxies, unsafe server URLs,
malformed session/call credentials and TLS failures. Plain HTTP requires an
explicit loopback-only development opt-in.

Native plugins run with the desktop user's authority. Enable only reviewed
plugins from a trusted distribution channel, verify their SHA-256 manifest
and prefer signed release artifacts. A matching hash proves package
integrity, not publisher identity.

Server-side authorization remains authoritative. Keep the Editor endpoint
behind HTTPS, a private administration network/VPN, Host/IP policy and a
firewall. Remove the one-time `EDITOR_TOKEN` after founder setup and keep
remote Python-hook editing disabled unless every permitted operator is fully
trusted.
