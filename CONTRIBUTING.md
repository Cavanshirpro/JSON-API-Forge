# Contributing to JSON API Forge Editor

Read `LICENSE`, `LICENSE-FAQ.md`, `GOVERNANCE.md` and
`CONTRIBUTOR_LICENSE_AGREEMENT.md` before contributing. Report vulnerabilities
through `SECURITY.md`; do not disclose credentials or exploit details in a
public issue.

The Editor branch must remain Editor-only. Do not add the Python server, SDK,
example projects, deployment templates or their workflows here.

## Required local checks

```bash
cmake -S . -B build/editor -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DFORGE_EDITOR_WARNINGS_AS_ERRORS=ON
cmake --build build/editor --parallel
ctest --test-dir build/editor --output-on-failure
python scripts/check_manifest.py
git diff --check
```

Test success and failure paths for security-sensitive changes. Never persist
passwords, founder setup secrets, bearer sessions or call tickets. Native
plugin changes must preserve path containment, no-symlink, digest, API-version,
declared-permission and explicit-enable checks.

Pull requests should explain behavior, compatibility, security impact, tests
and packaging impact. Contribution forks are permitted only within the narrow
collaboration exception described by the project license.
