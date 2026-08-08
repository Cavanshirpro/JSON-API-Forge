# cPanel deployment guide

JSON API Forge is an **ASGI** FastAPI application. cPanel's standard Application Manager is built around Phusion Passenger; cPanel's current documentation describes Passenger application registration and Python WSGI deployment. This repository therefore includes `passenger_wsgi.py`, using `a2wsgi` as an ASGI→WSGI compatibility bridge for ordinary HTTP APIs.

> Passenger/WSGI mode is not the preferred runtime for WebSockets and other long-lived ASGI connections. If realtime messaging, SSE at scale, many workers or high concurrency matters, use native Uvicorn/Hypercorn behind Nginx/Apache reverse proxy on a VPS/platform that supports ASGI directly.

Official references checked for this guide (August 2026):

- cPanel “Using Passenger Applications”: `https://docs.cpanel.net/knowledge-base/web-services/using-passenger-applications/`
- cPanel “Application Manager”: `https://docs.cpanel.net/cpanel/software/application-manager/`
- cPanel “How to Install a Python WSGI Application”: `https://docs.cpanel.net/knowledge-base/web-services/how-to-install-a-python-wsgi-application/`

## 1. Upload and extract

Recommended layout:

```text
/home/CPANEL_USER/json-api-forge/
├── framework/
├── app/
├── docs/
├── main.py
├── passenger_wsgi.py
├── requirements.txt
└── .env
```

Avoid placing `.env` under `public_html`.

## 2. Select Python

Use the newest supported Python 3 version provided by the host that satisfies the dependency versions. Create/activate the virtual environment provided by Application Manager/Setup Python App or your shell.

## 3. Install dependencies

```bash
cd ~/json-api-forge
pip install --upgrade pip
pip install -r requirements.txt
```

If your host does not offer Redis, leave cache/rate-limit/realtime on memory mode and understand that those states are process-local.

## 4. Configure `.env` safely

Do **not** copy a known example admin password. v0.4 keeps secret values blank in `.env.example`. Generate a gitignored file first:

```bash
forge init --production
```

Then edit deployment-specific DB/Redis URLs or import equivalent values through cPanel Application Manager environment variables / your hosting secret mechanism:

```env
APP_ENV=production
APP1_BOOTSTRAP_ADMIN_KEY=<long-random-secret>
JWT_SECRET=<long-random-secret>
APP1_DATABASE_URL=postgresql+asyncpg://user:password@host:5432/database
INTERNAL_DATABASE_URL=postgresql+asyncpg://user:password@host:5432/forge_internal
REDIS_URL=redis://127.0.0.1:6379/0
```

A dedicated internal PostgreSQL database/schema is preferable to SQLite when Passenger may start multiple processes because API-key/bootstrap state, audit metadata and media metadata may be shared. v0.4 operation idempotency itself lives in the selected **business database** so its record can commit atomically with SQL side effects.

## 5. Choose cPanel-safe project settings

For a shared host without Redis:

```json
{
  "cache": {"backend":"memory"},
  "rate_limit": {"backend":"memory"},
  "realtime": {"backend":"memory"}
}
```

For a host/VPS with Redis:

```json
{
  "cache": {"backend":"tiered"},
  "rate_limit": {"backend":"redis"},
  "realtime": {"backend":"redis"}
}
```

Redis mode is required when independent workers must share rate-limit buckets, cache generations and realtime channels.

## 6. Register the application

In cPanel Application Manager, register the extracted application path and target domain/base URI. Use `passenger_wsgi.py` as the WSGI startup file when the UI/provider expects one. The exported callable is named `application`.

Some hosts expose the same concept through CloudLinux “Setup Python App”. Field names differ by provider; the key requirements are the correct application root, virtualenv and Passenger entrypoint.

## 7. Validate before restart

```bash
forge validate
forge doctor --production
forge routes
python -m compileall framework app main.py passenger_wsgi.py
pytest -q
```

You can locally test native ASGI with:

```bash
python run.py
```

## 8. Restart Passenger

Use the cPanel restart action. cPanel's command-line WSGI guide also documents Passenger's conventional `tmp/restart.txt` mechanism, but use the hosting UI/provider instructions when available.

## 9. Verify

```text
https://api.example.com/health
https://api.example.com/ready
https://api.example.com/api/app1/v1/_docs
```

## 10. Resource sizing

Shared hosting accounts often have strict RAM/CPU/process caps. Do **not** assume these values should all be large:

```text
max_concurrent_requests
DB pool_size
DB max_overflow
HTTP max connections
Redis connections
```

A 20-connection DB pool per process with 10 Passenger processes can imply roughly 200 potential DB connections. Calculate pool limits across processes and compare them with the PostgreSQL/MySQL server's connection limit.

## 11. Realtime warning

The package contains WebSocket and SSE endpoints, and Redis can make their event state cross-worker. That does not make a WSGI bridge an ideal transport for WebSockets. Use native ASGI for serious realtime workloads.

## 12. Recommended upgrade path

```text
Small HTTP API
cPanel Passenger + PostgreSQL
        ↓
More workers
cPanel/VPS + PostgreSQL + Redis
        ↓
Heavy API / realtime
Nginx → Uvicorn workers → Forge
             ├─ PostgreSQL
             ├─ Redis
             └─ object storage/CDN
```


## 13. Current cPanel/Passenger notes (v0.4)

As of the documentation revision used for v0.4, cPanel Application Manager deploys applications through Phusion Passenger and allows application environment variables; cPanel's Python WSGI guide still documents `passenger_wsgi.py`, virtual environments, `requirements.txt`, and the Passenger `tmp/restart.txt` restart mechanism. The hosting provider can disable Application Manager, so availability is account/provider-specific.

Forge's compatibility bridge is therefore a pragmatic **HTTP** deployment option, not an attempt to turn WSGI into native ASGI. If the application depends on WebSocket semantics, long-lived SSE, large concurrent uploads or high worker counts, move the runtime behind a native ASGI server rather than designing around Passenger limitations.

## 14. cPanel production checklist

- Application Manager/Passenger enabled by the provider.
- Python version satisfies `pyproject.toml` (`>=3.11`).
- Virtual environment contains `requirements.txt` dependencies.
- `.env` is outside public/static directories and not downloadable.
- `forge doctor --production` has no errors.
- PostgreSQL/MySQL host permits the required outbound connection and pool count.
- Redis is reachable if Redis-backed features are configured.
- `passenger_wsgi.py` is the expected entry point and imports cleanly.
- `/health` and `/ready` behave correctly after restart.
- Logs are writable/rotated without exposing credentials.
- WebSocket/realtime requirements have been evaluated separately; if they are important, use native ASGI.
