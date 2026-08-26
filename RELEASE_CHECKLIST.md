# exampleApps v0.5.0 release checklist

- [ ] The branch is `exampleApps` and contains no server, SDK, Editor, deployment, schema or server-test tree.
- [ ] Exactly 25 project directories are present and `generate_example_catalog.py --check` passes.
- [ ] `VERSION` is exactly `0.5.0` and `MANIFEST.sha256` verifies.
- [ ] Python tooling compiles and passes Ruff.
- [ ] All projects validate and pass full smoke tests against a separate `main` checkout on Python 3.11–3.14.
- [ ] Bash and PowerShell installers pass on native Linux and Windows workers.
- [ ] Two independently produced ZIPs compare byte-for-byte.
- [ ] CodeQL and all required Action jobs are green.
- [ ] The downloaded ZIP matches its external checksum and its internal `SHA256SUMS` verifies.
- [ ] No `.env`, credentials, databases, media, logs, caches or build output is included.
- [ ] Publish only the unchanged artifact from the reviewed commit; do not release while CI is red.
