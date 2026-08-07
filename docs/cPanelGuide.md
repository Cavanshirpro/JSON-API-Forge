# cPanel deployment guide

JSON API Forge is an ASGI application. Many cPanel Python deployments are hosted through Phusion Passenger; CloudLinux Python Selector also uses Passenger. The repository includes `passenger_wsgi.py`, which uses `a2wsgi` to bridge the FastAPI ASGI app into Passenger's WSGI-style entrypoint.

> WebSockets and other long-lived ASGI-native features are not a good fit for this bridge. For real-time messaging/game sockets, use Uvicorn/Hypercorn behind a reverse proxy on a VPS or a hosting plan that exposes native ASGI.

## 1. Upload

Upload and extract the project to a directory such as:

```text
/home/CPANEL_USER/json-api-forge/
```

Do not place `.env` in `public_html` if you can avoid it.

## 2. Create the Python application

Depending on the host, the cPanel UI may show **Setup Python App** (CloudLinux Python Selector) or an application/Passenger manager. Create an app rooted at the extracted project directory. Choose the newest Python 3 version offered by your host that is compatible with the requirements.

Use `passenger_wsgi.py` as the startup file/entrypoint when the UI requests one. The callable exported by the file is named `application`.

## 3. Install dependencies

Open the terminal supplied by cPanel or activate the virtual environment shown by Setup Python App, then run:

```bash
cd ~/json-api-forge
pip install -r requirements.txt
```

CloudLinux installations can also expose a requirements-file installation operation through their Python Selector tooling.

## 4. Configure environment

Copy the example:

```bash
cp .env.example .env
```

Set strong values for:

```env
APP1_BOOTSTRAP_ADMIN_KEY=...
APP2_BOOTSTRAP_ADMIN_KEY=...
JWT_SECRET=...
INTERNAL_DATABASE_URL=...
APP1_DATABASE_URL=...
APP2_DATABASE_URL=...
REDIS_URL=...
```

For cPanel production, prefer PostgreSQL/MySQL over SQLite when traffic is concurrent. Use database credentials created from the cPanel database tools or an external managed database.

## 5. Redis/cache choice

Many shared cPanel plans do not include a private Redis service. If Redis is unavailable, set each project's cache/rate-limit backend to `memory`. That is correct only for a single process/worker. If your host runs several independent Passenger processes, memory rate limits and caches are not globally consistent.

When Redis is available, use `tiered` cache and `redis` rate limiting for shared state across workers.

## 6. Validate before restart

```bash
python scripts/validate_config.py
python -m compileall framework app main.py passenger_wsgi.py
```

If your environment permits local execution, you can also test with:

```bash
python run.py
```

## 7. Restart Passenger

Use the cPanel application's Restart action. Some Passenger environments also restart after touching the conventional restart marker used by the hosting provider; prefer the UI unless your provider documents another method.

## 8. Verify

Open:

```text
https://your-domain.example/health
https://your-domain.example/ready
https://your-domain.example/docs
```

App routes remain separated:

```text
/api/app1/v1/...
/api/app2/v1/...
```

## 9. Production notes

- Set exact CORS origins and trusted hosts.
- Turn on HTTPS enforcement only after your proxy headers/scheme are correct.
- Never expose database or Redis ports publicly.
- Keep the bootstrap key private and issue ordinary per-plugin API keys.
- If the cPanel account has strict CPU/RAM/process limits, lower DB pool sizes and concurrency limits. Increasing them beyond the hosting account's real resources causes worse failure modes, not more throughput.
- Large media files should eventually move to object storage/CDN; local cPanel disk is suitable only for modest workloads.
- For high-volume WebSockets, background queues, video transcoding, many workers or horizontal scaling, move the runtime to a VPS/container platform and keep cPanel only for unrelated site hosting if desired.
