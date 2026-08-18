# Editor plugins

JSON API Forge Editor supports reviewed native Qt plugins and a catalog served by JSON API Forge itself. Discovery never enables code: the operator must approve a plugin ID from **Plugins → Manage plugins…** after placing its library and manifest in this directory or the per-user application-data `plugins` directory.

## Native manifest contract

Name the manifest `NAME.forgeplugin.json` and keep the referenced library beside it:

```json
{
  "id": "vendor.plugin-name",
  "name": "Plugin Name",
  "version": "1.0.0",
  "apiVersion": 2,
  "library": "PluginName.so",
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "permissions": [
    "workspace.read",
    "graph.nodes.register"
  ]
}
```

Use `.dll` on Windows and `.dylib` on macOS. `sha256` is the lowercase digest of the exact native library. The manifest and library may not be symlinks; the canonical library path must stay inside the manifest directory. IDs and permission names use lowercase dotted identifiers and the permissions list is capped at 32 entries.

The library implements `ForgeEditor::IEditorPlugin` from `include/forgeeditor/IEditorPlugin.hpp`, declares `dev.jsonapiforge.EditorPlugin/2.0`, and returns `ForgeEditor::PluginApiVersion`. During `initialize`, the host supports:

```cpp
host->addPaletteComponent("Queue", "Resources", queueFragment);
host->addGraphNodeType("Validated Queue Publish", "vendor.queue.publish", defaultProperties);
host->addToolAction(action);
host->addDockWidget(Qt::RightDockWidgetArea, dock);
host->showStatusMessage("Queue tools ready");
```

Plugin-declared permissions are review metadata, not an operating-system sandbox. The Editor rechecks manifest/API/runtime identity and hashes the full binary before `QPluginLoader` executes it.

## Forge-backed catalog

The catalog browser calls a standard resource endpoint:

```text
GET /api/<catalog-project>/v1/<resource>?limit=100&offset=0
X-API-Key: <catalog-reader-key>
```

Each item must contain:

```json
{
  "plugin_id": "vendor.plugin-name",
  "name": "Plugin Name",
  "version": "1.0.0",
  "publisher": "Vendor",
  "download_url": "https://downloads.example/plugin-name-1.0.0.zip",
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "permissions": ["workspace.read", "graph.nodes.register"],
  "enabled": true
}
```

The v0.5.0 Editor validates a maximum of 100 records/2 MiB, safe identity fields, unique plugin-version pairs, HTTPS package URLs, SHA-256 metadata and bounded permission arrays. It rejects TLS errors, redirects, URL credentials and non-loopback cleartext endpoints. The catalog UI copies the reviewed package URL but intentionally does not auto-install or auto-enable native code. The `EditorPluginRegistry` project on the `exampleApps` branch is a ready Forge catalog backend.

For distribution, publish reproducible source, per-platform binaries, checksums and a cryptographic publisher signature through a trusted channel. SHA-256 proves that a reviewed file did not change; it does not prove who created it.
