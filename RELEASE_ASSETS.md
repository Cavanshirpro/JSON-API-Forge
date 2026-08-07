# GitHub Release Assets

## Do normal releases need an extra ZIP?

For the current JSON API Forge releases, **no additional ZIP or compiled binary is required**.

GitHub automatically provides **Source code (zip)** and **Source code (tar.gz)** for every release/tag. Because JSON API Forge is currently a Python source framework rather than a compiled end-user executable, those automatic source archives are sufficient for v0.1.0, v0.2.0, and v0.3.0.

The GitHub-ready ZIP used to create a tagged commit is a publishing/import package. Once its exact contents are committed and tagged, uploading the same ZIP again as a release asset is normally redundant.

## What should be on the release page now?

For each release:

1. Create the version tag (`v0.1.0`, `v0.2.0`, or `v0.3.0`).
2. Create a GitHub Release from that tag.
3. Use the version's `RELEASE.md` as the release description.
4. Let GitHub provide its automatic source ZIP and tarball.
5. Do not attach compiled files unless you intentionally create and support them.

## When should extra release assets be added later?

Attach additional assets only when they provide something the automatic source archives do not, for example:

- a standalone compiled CLI executable;
- a signed installer;
- an official Docker/OCI image reference or exported image archive;
- a Python wheel/sdist when JSON API Forge becomes an installable package;
- generated SDK bundles;
- an offline documentation bundle;
- database migration bundles that are intentionally distributed separately;
- cryptographic checksums/signatures/attestations for owner-published artifacts.

If you publish a custom binary/archive later, publish a checksum (for example SHA-256) and, ideally, a cryptographic signature or provenance/attestation as well.

## Important licensing note

Only the Project Owner or an authorized successor may publish Official Release assets under the JSON API Forge license. GitHub's automatic archives are tied to the official tagged repository state and are therefore the simplest release format for the current source-only project.
