# Start Here

JSON API Forge is a config-first FastAPI backend runtime. The normal workflow is: create a project under `app/<Name>/`, split configuration into numbered JSON fragments, validate it, inspect generated routes/OpenAPI, add Python hooks only where declarative behavior is not enough, then run explicit production checks.

## First run
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
forge init
forge validate
forge doctor
forge dev
```
`forge init` creates a gitignored `.env` with generated secrets. Do not copy a public placeholder as a real production secret.

## Mental model
A directory containing `app.json` is one project. `config/*.json` files are merged alphabetically. The result is parsed by strict Pydantic models (`extra=forbid`), expanded by feature packs, and used to build project-scoped runtime services and routes. Each project gets its own API prefix and declarative resources. Python hooks remain explicit imports from that project.

## Recommended reading order
Read architecture and multi-project configuration next, then security, databases, operations, data sources, media/realtime, CLI/testing, and finally production/failure-mode documents. `docs/README.md` contains the index.

## v0.4.1 note
Only explicit project directories are valid project roots. The obsolete root `app/config` and `app/hooks` layout was removed. If you carried forward an early single-project prototype, move its configuration/hook files into `app/<Project>/` before upgrading.
