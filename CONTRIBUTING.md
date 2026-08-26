# Contributing to JSON API Forge

Thank you for improving the canonical JSON API Forge project. The project is source-available and centrally governed; contributions are accepted upstream while alternative public distributions are restricted by `LICENSE`.

## Before you start
1. Read `LICENSE`, `LICENSE-FAQ.md`, `GOVERNANCE.md` and `CONTRIBUTOR_LICENSE_AGREEMENT.md`.
2. Open an issue before substantial architecture changes.
3. Use `SECURITY.md` for vulnerabilities.

## Contribution forks
The license provides a narrow collaboration-platform fork exception solely for preparing pull requests. Do not publish releases, packages, images, mirrors or separately maintained editions from such a fork.

## Development
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff format --check json_api_forge tests contract-tests scripts
ruff check json_api_forge tests contract-tests scripts
python -m compileall -q json_api_forge tests contract-tests scripts
pytest --cov=json_api_forge --cov-report=term-missing -q tests
python scripts/check_manifest.py
```

Add tests for success, failure, bounds and concurrency behavior when relevant. Server behavior belongs on `main`; this branch accepts only SDK code, tests, packaging and SDK documentation.

A pull request should explain motivation, behavior, compatibility, tests and documentation. Submission is governed by the project CLA when acknowledged in the PR workflow.
