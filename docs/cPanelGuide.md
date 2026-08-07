# cPanel deployment guide

## Important compatibility note

FastAPI is an **ASGI** framework. Traditional cPanel Python applications commonly run through **Phusion Passenger**, whose standard Python application path is WSGI-oriented. This project includes `passenger_wsgi.py` using `a2wsgi.ASGIMiddleware` so normal HTTP FastAPI endpoints can run in that environment.

Features that depend on native ASGI behavior, especially WebSockets, should be hosted with Uvicorn/Hypercorn on a VPS or another ASGI-capable service and placed behind a reverse proxy instead of relying on the Passenger WSGI bridge.

## Before uploading

Your hosting plan needs Python application support. Depending on the host, cPanel may expose **Setup Python App** (CloudLinux Python Selector) or **Application Manager**/Passenger. If neither is available, shared hosting may not support this deployment and you will need the host to enable it or use a VPS.

## Method A — Setup Python App / CloudLinux Python Selector

1. Upload/extract the project somewhere under your account, preferably outside `public_html`, e.g. `~/apps/json_api_forge`.
2. In cPanel open **Setup Python App**.
3. Create an application using the newest Python version your host offers that is compatible with the dependencies (Python 3.11+ is a good target).
4. Set the application root to the project directory.
5. Set application URL/domain/subdomain.
6. Set startup file to `passenger_wsgi.py`.
7. If the panel asks for an entry point, use `application`.
8. Create environment variables in the panel or upload a protected `.env` file in the application root.
9. Activate the virtual environment command shown by cPanel.
10. Install dependencies:

```bash
pip install -r requirements.txt
```

11. Restart the application from the cPanel UI.

## Method B — cPanel Application Manager / Passenger

If your host exposes Application Manager, register the Python app there. Keep `passenger_wsgi.py` at the application root. The exact Python executable/virtual-environment path can vary by provider; follow the path cPanel creates for that application.

## `.env` example for cPanel

```env
APP_ENV=production
CONFIG_DIR=app/config
BOOTSTRAP_ADMIN_KEY=replace-with-a-long-random-value
JWT_SECRET=replace-with-another-long-random-value
INTERNAL_DATABASE_URL=postgresql+asyncpg://...
PRIMARY_DATABASE_URL=postgresql+asyncpg://...
LOG_LEVEL=INFO
```

Do not place `.env` in a publicly downloadable directory. Prefer cPanel's environment-variable UI when it is available.

## Database hosting

If PostgreSQL/MySQL is on the same hosting account, use the hostname/user/database values supplied by cPanel. If Supabase or another remote database is used, the hosting provider must allow outbound connections to its port/host.

Some shared hosts block arbitrary outbound ports. If connection fails despite correct credentials, ask the provider whether outbound PostgreSQL/MySQL connections are allowed.

## Restart after changes

Passenger applications may require an explicit restart from cPanel. On installations using the classic Passenger convention, touching `tmp/restart.txt` can trigger a restart:

```bash
mkdir -p tmp
touch tmp/restart.txt
```

Use the cPanel UI restart action if your provider supplies one.

## Recommended production URL layout

Use a dedicated subdomain such as:

```text
api.example.com
```

instead of mixing the API application with static files under the website root.

## Test after deployment

```text
GET /health
GET /docs
```

Then create a normal API key through `/api/v1/admin/api-keys` using the bootstrap key.

## Common problems

### 500 error immediately

Check Passenger/application logs. Common causes are missing dependencies, wrong startup filename, wrong entry point, unsupported Python version, invalid JSON or missing environment variables.

### `ModuleNotFoundError`

Dependencies were installed into a different Python environment. Activate the environment shown by cPanel, then rerun `pip install -r requirements.txt`.

### Database connection timeout

Check remote-host allowlists/firewall/outbound restrictions and whether the database requires TLS.

### WebSocket does not work

Expected in WSGI bridge mode. Use a native ASGI deployment for WebSockets.

### SQLite locks under traffic

Use PostgreSQL/MySQL for production concurrent workloads.

## Current official references used when preparing this guide

- cPanel — How to Install a Python WSGI Application: https://docs.cpanel.net/knowledge-base/web-services/how-to-install-a-python-wsgi-application/
- cPanel — Using Passenger Applications: https://docs.cpanel.net/knowledge-base/web-services/using-passenger-applications/
- CloudLinux — Python Selector documentation: https://docs.cloudlinux.com/cloudlinuxos/cloudlinux_os_components/

Hosting providers customize cPanel, so names and available Python versions can differ even when the underlying Passenger/Python Selector model is the same.
