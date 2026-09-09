# Contributing to JSON API Forge examples

Read `LICENSE`, `LICENSE-FAQ.md`, `GOVERNANCE.md` and `CONTRIBUTOR_LICENSE_AGREEMENT.md` before contributing. Use `SECURITY.md` for vulnerabilities.

This branch accepts only project content under `app/`, example documentation, and the generator/installer/smoke/package tooling needed to verify that content. Server changes belong on `main`; SDK changes on `python-library`; desktop changes on `Editor`.

```bash
python scripts/generate_example_catalog.py --check
python -m compileall -q scripts
bash -n scripts/install-example.sh
python scripts/build-example-bundle.py /tmp/examples.zip
python scripts/check_manifest.py
```

For full behavior validation, copy `app/` into a clean v0.5.1 `main` checkout, run `forge init`, `forge validate`, `forge doctor`, then execute `scripts/smoke-example-apps.py` from that server checkout as the Action does.

Pull requests should explain the use case, security model, routes, roles, data lifecycle and test coverage. Never add real secrets or personal/customer data.

## Provenance and AI assistance

Follow [AI_USAGE_POLICY.md](AI_USAGE_POLICY.md). Identify material AI assistance and third-party code/assets, preserve upstream notices, and record human review and tests. Read [TRADEMARK_POLICY.md](TRADEMARK_POLICY.md) before using the project identity in an integration or contribution fork.
