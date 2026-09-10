# Editor v0.5.1 — workflow and installer repair

This source package changes only the Editor component. The product version remains 0.5.1.
Baseline: `342fd4c7a7862c1c630e2e091c14a32159445373` on the `Editor` branch.

## Confirmed failures and fixes

The [Editor build run](https://github.com/YoungLionOrganization/JSON-API-Forge/actions/runs/34378732238)
failed on Linux ARM64 because IFW 4.8.1's `binarycreator` needs `libtiff.so.5`,
whereas Ubuntu 24.04 provides the TIFF 6 ABI. The workflow now obtains the
SHA256-pinned Ubuntu compatibility package and exposes it only to that tool.
The Editor's application runtime and the system library installation are unchanged.
The build tool is started immediately after setup to catch loader failures early.

macOS Intel installed IFW successfully, then failed with `hdiutil: Resource busy`
on detaching the downloaded DMG. Cleanup now retries, then force-detaches only
that temporary mount. A remaining cleanup failure is reported as a warning;
missing or unusable IFW tools still fail the job.

The installer had put the full 1024x1024 brand image in `QWizard::LogoPixmap`.
[Qt's configuration reference](https://doc.qt.io/qtinstallerframework/ifw-globalconfig.html)
identifies this as a wizard pixmap, rather than an automatically fitted app icon.
All three installer configurations now use the standard title/content layout
without header/background pixmaps. Branding remains in the window/application
icons. Welcome, destination selection, license and navigation controls have room.

Both installer builders reject a stage missing the Editor executable. Linux and
Windows CI install the generated setup into a temporary destination and launch
the installed Editor for a screenshot smoke test. Linux bundling also handles
RPATH dependencies that already point to the destination file.

## Upload this folder only

Extract this ZIP into a new folder. Open PowerShell in the extracted
`JSON-API-Forge-Editor-v0.5.1` directory and run:

```powershell
.\PUSH-EDITOR.bat
```

Type `YUKLE` after the source checks. Requires Git for Windows and Windows
PowerShell. The script uses Git's existing GitHub authentication, uploads only
`refs/heads/Editor`, keeps the current remote Editor commit as its parent and
performs a normal push. It does not change your source folder, other branches,
tags or releases. If someone updates Editor concurrently, the push is rejected
instead of overwriting that update. Rerun after reviewing the remote change.

For source verification without any GitHub operation:

```powershell
.\PUSH-EDITOR.bat --check
```

Do not rerun the older four-branch uploader to publish this Editor-only repair.

## Verification

- Qt 6.8.3 Linux Release build with warnings treated as errors and native tests.
- Installer layout/empty-stage/DMG-cleanup regression tests.
- Real Qt IFW 4.8.1 Linux setup created; GUI opened at 760x540 on a 1366x768
  display, with visible navigation. Next advances to destination selection.
- Generated setup installed; the installed Editor launched and saved its screenshot.
- Windows uploader PowerShell payload and local Git upload checks.
- Source manifest and final ZIP byte verification.

The remote workflow has not been rerun for these unpushed changes. Native Windows,
macOS and ARM64 validation still runs in GitHub Actions after you upload this folder.
The source ZIP contains build/packaging sources, not a prebuilt Windows installer.
