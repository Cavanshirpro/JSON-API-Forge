# Contributing to JSON API Forge

Thank you for improving the canonical JSON API Forge project. The project is source-available and centrally governed; contributions are accepted upstream, while alternative public distributions are restricted by `LICENSE`.

## Before you start

1. Read `LICENSE`, `LICENSE-FAQ.md`, `GOVERNANCE.md` and `CONTRIBUTOR_LICENSE_AGREEMENT.md`.
2. For substantial architectural changes, open an issue first so the design can be discussed before implementation.
3. For security vulnerabilities, follow `SECURITY.md` rather than opening a public exploit report.

## Contribution forks

The license contains a narrow exception allowing a collaboration-platform fork solely to prepare and submit a pull request to the canonical repository. That exception does not permit releases, packages, Docker images, mirrors, a separately maintained edition or other alternative distribution from the fork.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
forge init
```

Never commit the generated `.env` file.

## Validate changes

```bash
forge validate
forge doctor
forge schema
git diff --exit-code -- schemas
python -m compileall -q framework app tests
pytest --cov=framework --cov-report=term-missing -q
```

Add or update tests for behavior changes, including failure/concurrency cases when relevant. Update generated JSON Schemas and documentation whenever declarative behavior changes. Keep security-sensitive business logic explicit and reviewable rather than hiding it in overly generic configuration.

## Pull requests

A pull request should explain the motivation, behavior change, compatibility impact, tests and documentation changes. The pull-request template includes an affirmative CLA checkbox. By checking it and submitting the PR, you accept `CONTRIBUTOR_LICENSE_AGREEMENT.md` for that contribution.

The Project Owner may request changes, decline a contribution or rework it before inclusion.
