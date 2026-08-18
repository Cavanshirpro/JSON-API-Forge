# JSON API Forge Editor

JSON API Forge Editor is a C++20/Qt 6 desktop workspace for authoring and operating Forge projects. It combines direct JSON editing, typed visual forms and an Unreal-inspired operation graph without introducing a second runtime language: the graph compiles to ordinary Forge configuration and the server still applies its normal schema, semantic and policy checks.

## Authoring modes

- **Code** provides line numbers, JSON highlighting, current-line focus and direct access to every supported local or remote document.
- **Visual** exposes resources, operations, databases and event channels as selectable, draggable components with typed and JSON property editing.
- **Graph** provides a grid canvas with pan/zoom, marquee selection, draggable nodes, output-to-input Bézier wires, cycle/fan-in validation, automatic layout, fit-to-content and a live compiled-operation preview.

The graph palette includes Request, Authorization, SQL Query, SQL Mutation, Branch, Transform, Forge Operation, Python SDK, Event and Response nodes. Native plugins can register additional node types through Plugin API v2. Branch/Transform/Event and custom plugin nodes remain explicit design nodes until a compiler exists for their semantics; compile preview reports them instead of silently dropping behavior. Graphs are stored as bounded, schema-versioned `graphs/*.forgegraph.json` documents and target one direct `config/*.json` fragment.

## Project templates

Use **File → New from template…** after opening a local workspace. Creation is staged in a temporary directory and atomically published only after every file succeeds. Each template includes a manifest, database/security/resource/operation/event fragments, an editable graph and its own runbook.

| Template | Focus |
|---|---|
| Secure Operations Hub | Hardened CRUD, permissions, cache, events and analytics |
| SaaS Control Plane | Tenant subscription and lifecycle operations |
| Event-Driven Commerce | Order workflow and idempotent processing foundation |
| Analytics Read Model | Bounded aggregate/read-model API |
| Forge Plugin Registry | Forge-backed Editor plugin catalog metadata |
| Python Enterprise Gateway | Multi-region Python SDK integration foundation |
| Media Operations | Media metadata and operational lifecycle |
| Audited Ledger Workflow | Controlled transitions and audit-oriented records |

## Local and remote workspaces

Choose **File → Open local workspace…** and select a Forge repository root, its `app/` directory or one project directory. Local JSON/graph saves use `QSaveFile` atomic replacement. The Editor performs structural checks; `forge validate` remains the canonical merged-project and semantic validator.

For remote administration, enable the control plane only on a private endpoint:

```dotenv
EDITOR_API_ENABLED=true
EDITOR_TOKEN=<strong-independent-secret>
EDITOR_REQUIRE_HTTPS=true
EDITOR_ALLOWED_IPS=10.20.0.0/16
EDITOR_TRUSTED_PROXY_CIDRS=10.0.0.0/8
EDITOR_ALLOWED_PROJECTS=Billing,InternalPortal
EDITOR_READ_ONLY=false
EDITOR_ALLOW_CREATE_PROJECTS=false
EDITOR_ALLOW_HOOKS=false
EDITOR_ALLOW_GRAPHS=true
```

The desktop token stays in memory and is cleared on disconnect/destruction; only the non-secret last URL is saved. Redirects, certificate failures and ambient desktop proxies are rejected. Plain HTTP requires a visible local-development opt-in and is restricted to loopback addresses. Keep the endpoint behind a VPN/private administration host and firewall. Python hook editing remains a separate, high-risk policy.

Remote graph support is deliberately metadata-only. The server checks document size, exact fields, node/edge identities, target path, unique input fan-in and acyclic execution. Compiled JSON must still pass normal Forge validation before deployment.

## Python SDK integration

Open **Integrations → Python SDK panel** to generate secret-safe snippets for:

- synchronous and asynchronous clients;
- bounded pagination and retry policy;
- multi-region rendezvous routing, failover and circuit breaking;
- YoungLion-native payloads;
- DDM conversion adapters.

The panel reads the API key from a named environment variable, invokes Python with fixed arguments rather than a shell, can verify the installed SDK and can run a bounded health check. Install the base SDK with `pip install json-api-forge`, or integration extras with `pip install "json-api-forge[younglion]"` and `pip install "json-api-forge[ddm]"`.

## Plugins and Forge catalog

Local native plugins can contribute palette components, graph node types, actions and dock widgets. A manifest must use API v2, declare a lowercase SHA-256 digest and list its requested permissions. The Editor constrains libraries to approved plugin directories, rejects symlinks and identity/API mismatches, verifies the binary digest before loading, and requires explicit per-ID enablement.

**Plugins → Browse Forge plugin catalog…** reads release metadata from a normal JSON API Forge resource (`/api/<project>/v1/<resource>`). This makes Forge itself the catalog/control plane: the response is bounded and every record's ID, version, HTTPS package URL, digest and permissions are validated. The Editor does not silently download or execute catalog code; an operator reviews the record and copies the package URL before installing the verified native bundle. See `editor/plugins/README.md` for the contracts.

Native plugins execute with the desktop user's privileges. Hash verification detects package changes but is not publisher identity; use signed releases and a trusted distribution channel.

## Build locally

Prerequisites are CMake 3.24+, a C++20 compiler, Qt 6.4+ with Core/Gui/Widgets/Network/Test, and preferably Ninja.

```bash
cmake -S . -B build/editor -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DFORGE_EDITOR_WARNINGS_AS_ERRORS=ON
cmake --build build/editor --parallel
ctest --test-dir build/editor --output-on-failure
cmake --install build/editor --prefix build/stage
QT_QPA_PLATFORM=offscreen build/editor/editor/JSON-API-Forge-Editor \
  --graph-preview --screenshot build/editor-graph-preview.png
```

The supplied project logo is embedded unchanged in the UI and converted to native Windows/macOS icons. Linux installs include a desktop entry and hicolor icon.

## CI artifacts

The `Editor build` workflow builds and tests six native targets with warnings-as-errors:

- Linux x64 and ARM64 (`ubuntu-24.04`, `ubuntu-24.04-arm`)
- Windows x64 and ARM64 (`windows-2025`, `windows-11-arm`)
- macOS x64 and ARM64 (`macos-15-intel`, `macos-15`)

Linux jobs render both welcome and graph screenshots. Windows runs `windeployqt`; macOS runs `macdeployqt`; every platform receives an architecture-specific archive and SHA-256 file. A final job verifies those hashes and publishes one all-platform bundle. Workflows never create a release or push generated binaries.
