# IoT Control Center

Device fleet control metadata, operator ownership, remediation workflows and realtime state notifications.

This is a deliberately substantial reference application: four SQL resources, scoped operator/auditor roles, soft deletion, cache and rate-limit policy, three transactional/analytics RPCs, an event channel, and an Editor operation graph.
## Run

```bash
forge init
forge validate
forge doctor
forge dev
```

Docs: `http://127.0.0.1:8000/api/iot-control-center/v1/_docs`

Before production, replace SQLite and in-memory coordination with managed PostgreSQL/Redis, restrict trusted hosts/origins, rotate bootstrap credentials, and review permissions. The domain content is synthetic and is not professional, medical, legal or financial advice.
