# JSON API Forge Editor v0.5.0

**Release date:** 25 August 2026

**Status:** Alpha desktop workspace

**License:** JSON API Forge Source-Available Self-Host License 1.1

v0.5.0 is the first complete Editor delivery line. It is a native C++20/Qt 6
workspace for local and policy-controlled remote Forge administration.

The release includes code, typed visual and graph editing; worker profiles;
ranked/scoped access; project areas; messaging, notes and attachments;
read-only database browsing; security audit visibility; and short-lived
audio/video call tickets. The Editor never substitutes UI visibility for
server authorization.

The `Editor build` workflow produces six portable, multi-file packages and six
installers:

| Target | Portable package | Installer |
|---|---|---|
| Linux x64 / ARM64 | ZIP | DEB |
| Windows x64 / ARM64 | ZIP | NSIS EXE |
| macOS Intel / ARM64 | ZIP | DMG |

Every deliverable has a SHA-256 sidecar, and the combined job verifies all
checksums before creating the all-platform artifact. Signing, notarization and
GitHub Release publication remain explicit Project Owner steps.

The server-side v0.5.0 control plane from `main` is required for remote team,
database and collaboration features. Keep that endpoint private, HTTPS-only
outside loopback, and configured with least-privilege project/document/
database policies.
