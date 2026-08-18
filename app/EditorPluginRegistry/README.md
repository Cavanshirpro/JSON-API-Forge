# Editor Plugin Registry

Forge-native Editor plugin metadata, publishers, permissions, HTTPS packages and SHA-256 review state; no automatic code execution.

This is a deliberately substantial reference application: four SQL resources, scoped operator/auditor roles, soft deletion, cache and rate-limit policy, three transactional/analytics RPCs, an event channel, and an Editor operation graph.
The `editor/plugins` resource matches the Editor's Forge catalog fields. Catalog reads never install or execute native code.

## Run

```bash
forge init
forge validate
forge doctor
forge dev
```

Docs: `http://127.0.0.1:8000/api/editor-plugin-registry/v1/_docs`

Before production, replace SQLite and in-memory coordination with managed PostgreSQL/Redis, restrict trusted hosts/origins, rotate bootstrap credentials, and review permissions. The domain content is synthetic and is not professional, medical, legal or financial advice.
