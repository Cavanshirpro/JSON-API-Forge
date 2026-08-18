# Installation

JSON API Forge requires Python 3.11–3.14 and Git. Python 3.13 is the recommended production baseline for v0.5.0.

## Clone and create an isolated environment

Linux/macOS:

```bash
git clone https://github.com/Cavanshirpro/JSON-API-Forge.git
cd JSON-API-Forge
./scripts/install.sh
source .venv/bin/activate
forge new MyService --slug my-service
forge init
forge validate
forge dev
```

Windows PowerShell:

```powershell
git clone https://github.com/Cavanshirpro/JSON-API-Forge.git
Set-Location JSON-API-Forge
.\scripts\install.ps1
.\.venv\Scripts\Activate.ps1
forge new MyService --slug my-service
forge init
forge validate
forge dev
```

Pass `--dev` (PowerShell: `-Dev`) to include tests and release tooling. The scripts never overwrite `.env` or application projects.

## Install directly from a Git ref

```bash
python -m pip install "json-api-forge @ git+https://github.com/Cavanshirpro/JSON-API-Forge.git@main"
mkdir my-forge-server && cd my-forge-server
forge new MyService --slug my-service
forge init
forge validate
forge dev
```

Pin a release tag or commit instead of `main` for reproducible deployment.

## Production checks

```bash
forge init --production
forge doctor --production
forge migrate
forge validate
```

Set `INTERNAL_SCHEMA_MODE=validate` after migration. Run behind a TLS reverse proxy, configure each project's trusted proxy CIDRs/hosts, and never commit `.env`.

## Branches

- `main`: runtime and CLI; intentionally no example app.
- `python-library`: runtime plus the typed Python client package and library artifact workflow.
- `Editor`: C++20/Qt 6 desktop editor and plugin SDK.
- `exampleApps`: copy-ready application directories validated against `main`.

Each branch README contains its own build commands.
