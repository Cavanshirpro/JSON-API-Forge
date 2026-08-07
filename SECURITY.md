# Security Policy

## Supported versions

| Version | Security support |
|---|---|
| 0.3.x | ✅ Current supported line |
| 0.2.x | ❌ Historical |
| 0.1.x | ❌ Historical |

Historical releases remain available for reproducibility and comparison, but security fixes are expected to target the current supported release line unless the Project Owner states otherwise.

## Reporting a vulnerability

Please do **not** publish exploit details, credentials, private keys or sensitive deployment data in a public issue.

1. Use GitHub's private **Report a vulnerability / Private Vulnerability Reporting** feature on the canonical repository when it is enabled.
2. If private reporting is not available, open a minimal public issue requesting a private security contact channel **without including exploit details**.
3. Include the affected version, deployment model, impact, reproduction conditions and a proposed mitigation if known.

The Project Owner may coordinate a fix and disclosure timeline. No guaranteed response time or security-support SLA is provided.

## Scope notes

Configuration mistakes, exposed `.env` files, weak keys, unsafe custom hooks, arbitrary SQL endpoints added by deployers, or insecure reverse-proxy/TLS configuration can create vulnerabilities outside the framework's default security boundary. Never commit real `.env` secrets.
