# Editor control plane

The desktop editor uses a separate management surface at `/__forge/editor/v1`. It is absent unless `EDITOR_API_ENABLED=true`. Application API keys, bootstrap keys, JWTs and the operator token cannot authenticate this surface; only `X-Forge-Editor-Token` is accepted.

## Server policy

```dotenv
EDITOR_API_ENABLED=true
EDITOR_TOKEN=<a separately generated 32+ character secret>
EDITOR_REQUIRE_HTTPS=true
EDITOR_ALLOWED_IPS=10.20.0.0/16,2001:db8:1234::/48
EDITOR_TRUSTED_PROXY_CIDRS=10.0.0.0/8
EDITOR_READ_ONLY=false
EDITOR_ALLOW_CREATE_PROJECTS=false
EDITOR_ALLOW_HOOKS=false
EDITOR_ALLOW_GRAPHS=false
EDITOR_ALLOWED_PROJECTS=Billing API,Internal Portal
EDITOR_MAX_DOCUMENT_BYTES=2097152
```

Forwarded protocol/IP headers are used only when the direct peer belongs to `EDITOR_TRUSTED_PROXY_CIDRS`. In production the process refuses to expose the API without HTTPS policy or with a weak/missing editor token.

## File boundary

The default writable set is `app.json` plus direct `config/*.json` fragments. Python `hooks/*.py` and Blueprint-style `graphs/*.forgegraph.json` each require their own explicit policy. Graph documents are bounded, schema-versioned editor metadata: node/edge identity, target paths, fan-in and acyclic execution constraints are validated server-side, and a graph never bypasses normal merged-project validation for the JSON it generates. `.env`, secrets, arbitrary source files, symlinks and traversal paths are never editor documents.

Reads return a SHA-256 revision. Writes must send that revision (or `new` for a new allowed document). A stale revision returns HTTP 409. JSON edits are staged into a private project copy and the complete merged configuration is validated before an atomic replacement; invalid edits return HTTP 422 without changing the live file.

Project creation, hook editing, project allowlists and read-only mode are server-enforced capabilities. The Qt client discovers them from `/capabilities` and disables unsupported controls rather than assuming authority.

## Recommended deployment

Expose this prefix only on a private administration hostname/VPN, terminate TLS at a trusted reverse proxy, restrict source networks at the firewall as well as the application policy, rotate the editor token separately, and keep `EDITOR_ALLOW_HOOKS=false` unless remote Python code editing is explicitly required. Run a single management worker or use editor-side conflict handling; SHA revisions prevent silent overwrites across workers but do not provide distributed locking.
