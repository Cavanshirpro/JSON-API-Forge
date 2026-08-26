# Build JSON API Forge Editor with Qt Creator

This guide builds the native Editor from the repository root and uses the checked-in `CMakePresets.json`. The presets are shared by Qt Creator and the command line, so both paths produce the same source configuration.

## 1. Install a matching toolchain

Install Qt 6.8.3 (Qt 6.4 or newer is supported) with these components:

- Qt Core, Gui, Widgets, Network and Test;
- Qt WebEngineWidgets when you want embedded call rooms;
- Qt Creator, CMake and Ninja;
- Qt Installer Framework under **Developer and Designer Tools** when you want to create the Windows setup executable.

Platform compiler requirements:

- **Windows x64:** Visual Studio 2022 Build Tools with **Desktop development with C++**, plus the `MSVC 2022 64-bit` Qt package.
- **Windows ARM64:** the Visual Studio 2022 ARM64 C++ tools and the `MSVC 2022 ARM64` Qt package. Do not mix x64 Qt libraries with an ARM64 kit.
- **macOS:** Xcode command-line tools and the Qt package matching the Mac architecture.
- **Linux:** GCC or Clang, Ninja, and the Qt 6 development packages. On Ubuntu, the CI-equivalent base is `qt6-base-dev qt6-base-dev-tools ninja-build`; `qt6-webengine-dev` is optional.

## 2. Register the Qt kit

1. Open **Edit → Preferences → Kits** (on macOS, **Qt Creator → Settings → Kits**).
2. Under **Qt Versions**, add the `qmake` or Qt installation discovered by the Qt Maintenance Tool if it is not already listed.
3. Under **Kits**, select a compiler whose architecture exactly matches that Qt installation.
4. Select the bundled or system CMake and Ninja tools. A healthy kit shows no red warning icon.

On Windows, start Qt Creator from the Qt installation or a Visual Studio developer environment if the MSVC compiler is not detected automatically.

## 3. Open and configure the project

1. Choose **File → Open File or Project**.
2. Open the repository-root `CMakeLists.txt`—not `editor/CMakeLists.txt` directly.
3. In **Configure Project**, select the matching kit.
4. Choose the checked-in **Developer build** (`dev`) preset for debugging or **Release build** (`release`) for a distributable binary.
5. Confirm that `BUILD_TESTING=ON`. Keep `FORGE_EDITOR_WARNINGS_AS_ERRORS=ON` so local builds enforce the same warning policy as CI.

Qt Creator should populate `build/dev` or `build/release`. If it instead proposes a shadow-build path, open **Projects → Build Settings → CMake** and select the corresponding preset.

## 4. Build, test and run

Select the `JSONAPIForgeEditor` target, then use **Build → Build Project**. The runnable executable is named `JSON-API-Forge-Editor` (`.exe` on Windows).

Run the tests from **Tools → Tests → Test Results → Run All Tests**, or use Qt Creator's terminal:

```bash
ctest --preset dev
```

Useful visual-regression launch arguments are:

```text
--window-size 1024x640 --screenshot editor-preview.png
--team-preview --window-size 1180x720 --screenshot team-preview.png
--graph-preview --window-size 1180x720 --screenshot graph-preview.png
```

## 5. Stage a portable build

From the repository root in Qt Creator's terminal:

```bash
cmake --build --preset release
ctest --preset release
cmake --install build/release --prefix build/stage
```

On Windows, deploy the Qt runtime next to the staged executable before creating a ZIP:

```powershell
$exe = Get-ChildItem build/stage -Filter JSON-API-Forge-Editor.exe -Recurse | Select-Object -First 1
windeployqt --release --no-translations --compiler-runtime $exe.FullName
Copy-Item EDITOR.md,LICENSE -Destination build/stage
Compress-Archive -Path build/stage/* -DestinationPath JSON-API-Forge-Editor-v0.5.0-windows-x64.zip
```

For ARM64, run these commands from the ARM64 kit and use an architecture-appropriate output name.

## 6. Build the Windows installer with Qt Installer Framework

Ensure `binarycreator.exe` from Qt Installer Framework is on `PATH`, then run:

```powershell
./editor/packaging/qtifw/build-installer.ps1 `
  -StageDir build/stage `
  -OutputFile JSON-API-Forge-Editor-v0.5.0-windows-x64-setup.exe
```

The helper consumes the same Qt IFW metadata as GitHub Actions. It embeds the staged application, application icons, Start Menu/Desktop shortcuts, maintenance/uninstall tool and the repository `LICENSE`. The license is shown as an agreement during setup and is also installed with the product.

## Troubleshooting

- **Qt6Config.cmake not found:** the kit does not point at the selected Qt installation. Fix the Qt version in the kit instead of hard-coding a machine-specific `CMAKE_PREFIX_PATH` into the repository.
- **Wrong machine type or linker errors:** the compiler architecture and Qt package architecture do not match. Delete the affected `build/dev` or `build/release` directory after correcting the kit, then configure again.
- **WebEngine is missing:** install Qt WebEngine for the exact Qt version/architecture. The Editor still builds without it and uses the secure external-browser fallback.
- **`binarycreator.exe` not found:** install Qt Installer Framework from the Qt Maintenance Tool and add its `bin` directory to the Qt Creator terminal environment.
- **Stale UI or resource output:** use **Build → Clean Project**, delete only the selected preset's build directory if needed, and reconfigure. Do not reuse one build directory across x64 and ARM64 kits.
