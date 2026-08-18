# Editor plugins

Native plugins are never enabled merely because a library is discovered. Place a reviewed plugin library and its manifest in this directory (or the user data `plugins` directory), then approve its ID from **Plugins → Manage plugins**.

Manifest name: `NAME.forgeplugin.json`

```json
{
  "id": "vendor.plugin-name",
  "name": "Plugin Name",
  "version": "1.0.0",
  "apiVersion": 1,
  "library": "PluginName.so"
}
```

Use `.dll` on Windows and `.dylib` on macOS. The library must remain inside the manifest directory, must not be a symlink and must implement `ForgeEditor::IEditorPlugin` from `include/forgeeditor/IEditorPlugin.hpp`. Plugin IDs/API versions are checked again after loading.

Native plugins execute with the desktop user's full privileges. This is an extension boundary, not a sandbox or signature system. Distribute source, checksums and signatures through a trusted channel; never approve an unknown binary.
