# Third-party notices

[LICENSE](LICENSE) (`LicenseRef-JAF-SASH-1.1`) applies to original JSON API Forge material. Section 7 preserves third-party terms and rights. Dependency versions are resolved per platform; this document identifies the main components and the release process, not an assertion that every resolved dependency has one license.

## Editor runtime

| Component | How used | License/source reference |
|---|---|---|
| Qt Core, Gui, Widgets, Network | Dynamically linked desktop/runtime modules; public APIs | [Qt licensing](https://doc.qt.io/qt-6/licensing.html), [qtbase source](https://github.com/qt/qtbase) |
| puff 2.3 (zlib v1.3.1) | Fixed-buffer raw DEFLATE decoder, statically linked; Mark Adler copyright and permissive terms retained | [Bundled source and provenance](editor/third_party/puff/README.md) |
| Qt Test | Build/test dependency | The matching Qt kit and source |
| Qt WebEngineWidgets, when available | Optional embedded call browser | [Qt WebEngine licensing](https://doc.qt.io/qt-6/qtwebengine-licensing.html), including Chromium and its third-party components |
| Qt Installer Framework 4.8.1 | Setup/maintenance wrapper | [Qt IFW documentation](https://doc.qt.io/qtinstallerframework/index.html); review the framework and its included components separately |
| Platform/native libraries | Qt plugins and deployed OS/runtime libraries | Exact selected Qt kit, package copyright files, compiler/runtime terms and bundled SBOMs |

Linux CI uses Ubuntu's Qt packages; Windows/macOS CI uses Qt 6.8.3. CMake supports Qt 6.4+ and uses the selected libraries from one kit. No commercial Qt license is implied by this repository.

## License copies and corresponding source

[editor/packaging/licenses](editor/packaging/licenses) contains unchanged upstream Qt copies of LGPLv3, GPLv3 and the Qt GPL exception from [qtbase v6.8.3](https://github.com/qt/qtbase/tree/v6.8.3/LICENSES). They are installed under `licenses/qt/`. Including these texts does not claim that every Qt or IFW component uses the same license or exception.

Under the applicable LGPL combined-work conditions, the project's original-code restrictions do not remove users' rights to modify/replace the LGPL library or debug such modifications. Keep dynamically linked Qt libraries replaceable and retain required notices, license texts, corresponding-source access and any applicable installation/relink information. A commercial Qt license or a different build/module choice may change the applicable route; assess the exact build. See [LGPLv3 section 4](editor/packaging/licenses/LGPL-3.0-only.txt).

The stage-notices helper copies available Qt-kit SBOM/license material and Ubuntu package copyright files into the payload and records the Qt version. A kit SBOM describes that kit and may include modules not shipped in the Editor; it is provenance input, not a claim that all listed modules are deployed. Missing upstream material still needs review, particularly Chromium/WebEngine and the IFW maintenance wrapper. Preserve corresponding source for the exact Qt/IFW versions and patches used; an unversioned homepage link is not a substitute for an applicable source-delivery obligation.

The Qt IFW agreement page presents the original Forge LICENSE. CMake and the workflow also install the supporting notices; displaying the project agreement does not ask the user to waive third-party rights. Native plugins have separate provenance and licensing obligations described in the [plugin guide](editor/plugins/README.md).

## Release and provenance records

Keep the exact source commit, dependency versions, upstream license texts/copyright notices and any local patches for the artifact being published. A permissive top-level package can contain subcomponents under other terms. Do not infer the license from a package name or an automated badge; use its installed metadata and corresponding upstream source.

Original project redistribution remains governed by LICENSE. Third-party licenses can impose separate notice, source or other obligations for components included in a binary, image or installer. A successful build does not by itself establish compliance. Review the exact payload before an official release and preserve required notices when repackaging it.
