# JSON API Forge example applications v0.5.0

This `exampleApps` branch contains only the 25 copy-ready Forge projects and the small tools that generate, install, smoke-test and package them. It intentionally contains no server runtime, Python SDK or Qt Editor source.

## Use an example

First obtain a v0.5.0 `main` checkout. Then copy one project from this branch into its `app/` directory:

```bash
./scripts/install-example.sh TaskBoard /path/to/JSON-API-Forge-main/app
```

Windows PowerShell:

```powershell
.\scripts\install-example.ps1 -Name TaskBoard -Destination C:\path\to\JSON-API-Forge-main\app
```

In the `main` checkout, create new local secrets and validate before starting:

```bash
forge init
forge validate
forge doctor
forge dev
```

The installers reject unsafe names, unknown projects and existing destinations. Do not copy a server `.env`, database, media or log directory between deployments.

## What is included

The collection covers CRUD, scoped roles, soft deletion, SQL/RPC, transactional idempotency, realtime events, media, public file data, operational workflows and Editor graph metadata. `EditorPluginRegistry` demonstrates reviewed plugin metadata and SHA-256 records; it never installs or executes native code.

See [EXAMPLE_APPS.md](EXAMPLE_APPS.md) for the full catalog and production caveats.

## Verification and release artifact

The branch workflow checks out `main` separately, installs its real runtime, copies all 25 projects into a clean `main/app/`, and runs validation plus schema/CRUD/RPC/idempotency/realtime/media smoke scenarios on Python 3.11–3.14. Bash and PowerShell copy installers run on native Linux and Windows workers.

`scripts/build-example-bundle.py` produces a bounded, symlink-free, byte-for-byte deterministic ZIP containing only `app/`, `EXAMPLE_APPS.md`, the two copy installers and an internal `SHA256SUMS`. GitHub Actions uploads the ZIP and its external checksum; it never publishes a Release automatically.

## License

JSON API Forge is source-available, not OSI open source. Review `LICENSE` and `LICENSE-FAQ.md` before use or redistribution. Official distribution authority remains with Cavanşir Qurbanzadə (`@Cavanshirpro`) or a lawful successor/assignee.
