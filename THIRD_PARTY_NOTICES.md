# Third-party notices

[LICENSE](LICENSE) (`LicenseRef-JAF-SASH-1.1`) applies to original JSON API Forge material. Section 7 preserves third-party terms and rights. Dependency versions are resolved per platform; this document identifies the main components and the release process, not an assertion that every resolved dependency has one license.

## Example sources and runtime

The catalog generator, copy installers and deterministic ZIP packager use Python, PowerShell and shell facilities. This source branch does not vendor the Forge server, Qt, the Python SDK, database servers or native Editor plugin binaries. Running the apps requires the independently distributed [main runtime](https://github.com/YoungLionOrganization/JSON-API-Forge/tree/main) and its dependencies; see that branch's [third-party notices](https://github.com/YoungLionOrganization/JSON-API-Forge/blob/main/THIRD_PARTY_NOTICES.md).

The built copy-ready ZIP includes the project license, notice, FAQ and policy documents as well as per-file checksums. `EditorPluginRegistry` stores metadata only: a catalog record, SHA-256 digest or example download URL does not license a plugin binary or prove its publisher's identity. Each actual plugin package needs its own dependency and license review.

Synthetic example data is provided with the original project material. No license to a real institution's data, identity or branding is implied by an example domain.

## Release and provenance records

Keep the exact source commit, dependency versions, upstream license texts/copyright notices and any local patches for the artifact being published. A permissive top-level package can contain subcomponents under other terms. Do not infer the license from a package name or an automated badge; use its installed metadata and corresponding upstream source.

Original project redistribution remains governed by LICENSE. Third-party licenses can impose separate notice, source or other obligations for components included in a binary, image or installer. A successful build does not by itself establish compliance. Review the exact payload before an official release and preserve required notices when repackaging it.
