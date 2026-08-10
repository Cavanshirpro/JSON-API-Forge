# GitHub Release Assets

For the current source-only JSON API Forge releases, no separately attached binary ZIP is required. GitHub automatically provides **Source code (zip)** and **Source code (tar.gz)** for each official tag. Those automatic archives are sufficient for v0.1.0 through v0.4.1.

For each release: create the version tag, allow the tag CI/release gate to pass, create the GitHub Release from that exact tag, and use `RELEASE.md` as the release description.

Extra assets should be added only when they add something GitHub's source archive does not: a compiled CLI, signed installer, intentionally supported wheel/sdist, generated SDK bundle, offline docs bundle or an explicit container artifact/reference. Owner-published custom artifacts should have SHA-256 and preferably provenance/signatures.

Only the Project Owner or an authorized successor may publish Official Release assets under the project license.
