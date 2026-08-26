# JSON API Forge Editor v0.5.0

<p align="center"><img src="editor/resources/logo.png" width="220" alt="JSON API Forge Editor logo"></p>

JSON API Forge Editor is the native C++20/Qt 6 desktop workspace for JSON API
Forge. It combines code editing, typed visual forms, a node graph, remote
database browsing and an account-based team workspace in the Amber Gold +
Graphite Gray design system.

This branch intentionally contains only the Editor. The canonical server and
remote control-plane implementation live on `main`; the Python SDK and
example applications have their own release branches.

## What v0.5.0 includes

- local and remote project/document editing with optimistic SHA-256 revisions;
- visual resource, operation, database and event-channel editing;
- bounded, schema-versioned operation graphs with cycle and fan-in checks;
- founder setup, worker sign-in, invitations, ranked roles and scoped access;
- profiles, open/restricted project areas, chat, notes and file sharing;
- policy-filtered, read-only Forge database browsing;
- audio/video room launch through short-lived call tickets;
- digest-verified Plugin API v2 and a bounded Forge plugin catalog;
- Python SDK snippet generation without putting API keys in generated source.

The desktop client does not treat hidden UI controls as authorization. The
server rechecks every project, document, database, membership and
collaboration request.

## Branding

The full background logo remains the application/window/platform icon. The
transparent, text-free mark in
`editor/resources/brand-mark-transparent.png` is used inside the interface
where a compact logo is appropriate.

## Build locally

Prerequisites: CMake 3.24+, a C++20 compiler, Qt 6.4+ Core/Gui/Widgets/Network
and Test, Ninja, and optionally Qt WebEngineWidgets.

```bash
cmake -S . -B build/editor -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DFORGE_EDITOR_WARNINGS_AS_ERRORS=ON
cmake --build build/editor --parallel
ctest --test-dir build/editor --output-on-failure
cmake --install build/editor --prefix build/stage
```

See [EDITOR.md](EDITOR.md) for the complete authoring, remote-team, plugin and
security model. For a click-by-click Qt Creator setup, matching kits, presets,
portable packaging and Qt Installer Framework steps, see
[QT-CREATOR-BUILD-GUIDE.md](QT-CREATOR-BUILD-GUIDE.md).

## GitHub Actions artifacts

The Editor workflow tests Linux, Windows and macOS on x64 and ARM64. Every
platform produces a multi-file portable ZIP plus a real installer:

| Platform | Portable | Installer |
|---|---|---|
| Linux x64 / ARM64 | `.zip` with bundled Qt runtime | `.deb` |
| Windows x64 / ARM64 | `.zip` deployed by `windeployqt` | Qt Installer Framework `-setup.exe` |
| macOS Intel / ARM64 | `.zip` deployed by `macdeployqt` | `.dmg` |

Each file receives a SHA-256 sidecar. The final job verifies every checksum
and publishes one all-platform ZIP for download from the Actions run. The
workflow never creates a GitHub Release automatically, so the Project Owner
can review and attach the artifacts to v0.5.0.

The Windows setup is built with Qt's own Installer Framework. It presents the
repository license before installation and installs the license alongside the
Editor.

## License

JSON API Forge is source-available, not OSI open source. Read
[LICENSE](LICENSE) and [LICENSE-FAQ.md](LICENSE-FAQ.md) before distribution or
commercial use.
