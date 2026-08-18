# Copy-ready example applications

This branch keeps complete Forge applications under `app/`; `main` intentionally contains none. Each directory is independent, uses its own slug/API prefix and can be copied unchanged into another JSON API Forge checkout.

| Application | Focus | Secret required |
|---|---|---|
| `TaskBoard` | Filtered/searchable SQL CRUD, soft deletion and scoped roles | `TASK_BOARD_BOOTSTRAP_ADMIN_KEY` |
| `GuildLedger` | Discord-style accounts plus atomic, idempotent balance operations | `GUILD_LEDGER_BOOTSTRAP_ADMIN_KEY` |
| `RealtimeSupport` | Ticket CRUD plus bounded WebSocket/SSE notifications | `REALTIME_SUPPORT_BOOTSTRAP_ADMIN_KEY` |
| `MediaLibrary` | Private local media, quotas, MIME/extension policy and collection metadata | `MEDIA_LIBRARY_BOOTSTRAP_ADMIN_KEY` |
| `PublicCatalog` | Explicitly public, read-only JSON-file data source with no secret | None |

## Run all examples in this branch

```bash
git clone --branch exampleApps --single-branch https://github.com/Cavanshirpro/JSON-API-Forge.git
cd JSON-API-Forge
./scripts/install.sh
source .venv/bin/activate                 # Windows: .\.venv\Scripts\Activate.ps1
forge init                               # creates strong local bootstrap secrets
forge validate
forge doctor
forge dev
```

The five documentation roots are `/api/task-board/v1/_docs`, `/api/guild-ledger/v1/_docs`, `/api/realtime-support/v1/_docs`, `/api/media-library/v1/_docs` and `/api/public-catalog/v1/_docs`.

## Copy one application into another checkout

From this branch:

```bash
./scripts/install-example.sh TaskBoard /path/to/JSON-API-Forge/app
# Windows PowerShell:
.\scripts\install-example.ps1 -Name TaskBoard -Destination C:\path\to\JSON-API-Forge\app
```

The scripts refuse to overwrite an existing target. A plain directory copy works too. In the destination checkout run `forge init`, `forge validate`, then `forge dev`. Never copy the generated root `.env` or runtime `data/`; create fresh secrets and databases per installation.

These are development/reference configurations. Before production, use Redis-backed shared rate limiting where needed, set concrete trusted hosts/CORS origins, enable HTTPS, move SQLite workloads to a supported production database and run `forge doctor --production`.
