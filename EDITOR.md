# JSON API Forge Editor

The editor is a C++20/Qt 6 Widgets application dedicated to JSON API Forge. It supports both local project trees and the v1 remote control plane implemented by the hardened server on this branch and `main`.

## Capabilities

- Code mode with line numbers, JSON syntax highlighting, current-line focus and indentation support.
- Visual mode with draggable resources, RPC operations, data sources and realtime channels; tree selection exposes editable typed/JSON properties.
- Local project discovery, atomic `QSaveFile` writes and JSON-object checks.
- Remote capability discovery, project/document browsing, creation when allowed, merged server validation and SHA-256 optimistic concurrency.
- Conflict-safe reload prompt on HTTP 409; invalid server-side edits never replace the live configuration.
- Server-enforced read-only, create-project, Python-hook, project allowlist, TLS/IP and size policies reflected in the UI.
- Native Qt plugin SDK with manifest/API/identity/path checks and explicit per-plugin approval.
- Graphite/amber QSS theme, animated workspace transitions, animated sidebar and startup fade.

The supplied project logo is embedded unchanged in the UI and converted into native Windows/macOS application icons. Linux installs include a desktop entry and hicolor application icon.

## Prerequisites

- CMake 3.24 or newer
- C++20 compiler (MSVC 2022, AppleClang 15+, GCC 12+ or Clang 15+)
- Qt 6.6 or newer with Core, Gui, Widgets, Network and Test
- Ninja is recommended for the included presets

## Build and test

```bash
cmake -S . -B build/editor -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DFORGE_EDITOR_WARNINGS_AS_ERRORS=ON
cmake --build build/editor --parallel
ctest --test-dir build/editor --output-on-failure
cmake --install build/editor --prefix build/stage
QT_QPA_PLATFORM=offscreen build/editor/editor/JSON-API-Forge-Editor --screenshot build/editor-preview.png
```

Or use `cmake --preset release`, `cmake --build --preset release` and `ctest --preset release`.

## Local workflow

Choose **File → Open local workspace** and select either a Forge repository root, its `app/` directory or one project directory. Local JSON saves are atomic. The editor performs syntax/object validation; run `forge validate` for the same full merged model/semantic validation used by the server.

## Remote workflow

Enable the server control plane only on an administration endpoint:

```dotenv
EDITOR_API_ENABLED=true
EDITOR_TOKEN=<strong independent secret>
EDITOR_REQUIRE_HTTPS=true
EDITOR_ALLOWED_IPS=10.20.0.0/16
EDITOR_TRUSTED_PROXY_CIDRS=10.0.0.0/8
EDITOR_ALLOWED_PROJECTS=Billing,Internal Portal
EDITOR_READ_ONLY=false
EDITOR_ALLOW_CREATE_PROJECTS=false
EDITOR_ALLOW_HOOKS=false
```

The desktop token is kept in memory and cleared on disconnect/destruction; only the non-secret last server URL is saved. Redirects and certificate errors are rejected. Ambient desktop/system proxies are disabled. Plain HTTP requires a visible local-development opt-in, is limited to `localhost`, `127.0.0.0/8` or `::1`, and may still be rejected by the server.

Keep the endpoint behind a VPN/private administration host and firewall. Remote hook editing is remote code modification and therefore disabled separately.

## Plugins

Plugins implement `ForgeEditor::IEditorPlugin` and may contribute palette components, tool actions and dock widgets. The editor scans only the installation/user plugin directories, reads `*.forgeplugin.json`, constrains the library to that directory, rejects symlinks/incompatible API versions and verifies runtime identity. A discovered plugin is not executed until the user enables its ID in **Plugins → Manage plugins**.

This is not a sandbox or code-signing system. A native plugin has the desktop user's privileges. Review and verify plugin source/binaries before approval. See `editor/plugins/README.md`.

## CI artifacts

The `Editor build` workflow compiles/tests with warnings-as-errors on Linux, Windows and macOS. It runs `windeployqt` and `macdeployqt` for self-contained platform bundles, emits the Linux install tree, uploads each platform artifact, then creates a single checksum manifest bundle. It never creates a release or pushes generated binaries.
