# Third-party notices

[LICENSE](LICENSE) (`LicenseRef-JAF-SASH-1.1`) applies to original JSON API Forge material. Section 7 preserves third-party terms and rights. Dependency versions are resolved per platform; this document identifies the main components and the release process, not an assertion that every resolved dependency has one license.

## Base and optional dependencies

| Component | Role | Upstream license record |
|---|---|---|
| HTTPX | Required HTTP transport | [HTTPX source](https://github.com/encode/httpx) |
| httpcore, AnyIO, certifi, idna and platform-selected transitives | Resolved transport/TLS/concurrency dependencies | Read each installed distribution's metadata and license files; [httpcore](https://github.com/encode/httpcore), [AnyIO](https://github.com/agronholm/anyio), [certifi](https://github.com/certifi/python-certifi), [idna](https://github.com/kjd/idna) |
| YoungLion 0.1.x | Optional `younglion` / `ddm` extras | Read the exact resolved YoungLion distribution; this project does not grant rights to it |
| Python and development tools | Runtime, tests, packaging, lint | [CPython notices](https://docs.python.org/3/license.html) and the `dev` declarations in [pyproject.toml](pyproject.toml) |

The SDK wheel does not vendor HTTPX, YoungLion or the Forge server. Installing optional extras can change the license inventory. Run `python -m pip inspect > dependency-environment.json` in the environment actually deployed and retain the corresponding distribution license files. The wheel and source distribution include this document with the original project license and policies.

## Release and provenance records

Keep the exact source commit, dependency versions, upstream license texts/copyright notices and any local patches for the artifact being published. A permissive top-level package can contain subcomponents under other terms. Do not infer the license from a package name or an automated badge; use its installed metadata and corresponding upstream source.

Original project redistribution remains governed by LICENSE. Third-party licenses can impose separate notice, source or other obligations for components included in a binary, image or installer. A successful build does not by itself establish compliance. Review the exact payload before an official release and preserve required notices when repackaging it.
