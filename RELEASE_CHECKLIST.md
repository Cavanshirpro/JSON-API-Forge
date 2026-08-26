# JSON API Forge Editor v0.5.0 release checklist

## Source

- [ ] The branch contains Editor source/assets/packaging only.
- [ ] CMake, VERSION, README, EDITOR and release metadata identify 0.5.0.
- [ ] The full icon and transparent in-app mark render correctly.
- [ ] `python scripts/check_manifest.py` passes.

## Security and behavior

- [ ] Session and call-ticket formats reject suffixes/control bytes.
- [ ] Redirect, proxy, TLS and loopback-only HTTP tests pass.
- [ ] Passwords/setup tokens/sessions are never persisted.
- [ ] Plugin path, symlink, digest, API and explicit-enable checks pass.
- [ ] Remote roles, database browsing, file sharing and calls are verified
      against a hardened v0.5.0 server.

## Build and packaging

- [ ] Warnings-as-errors CMake build and CTest pass on all six targets.
- [ ] Packaged-app screenshot smoke tests pass.
- [ ] Every portable ZIP contains more than 20 deployed files.
- [ ] Linux DEBs pass `dpkg-deb --info` and content inspection.
- [ ] Windows NSIS installers are created from the deployed staging tree.
- [ ] macOS DMGs contain the app and Applications shortcut and pass
      `hdiutil verify`.
- [ ] Every SHA-256 sidecar verifies in the combined job.
- [ ] Editor CodeQL is green.

## Publish

- [ ] Download and inspect the Actions artifacts.
- [ ] Complete platform signing/notarization where required.
- [ ] Attach portable ZIPs, installers and checksums to v0.5.0.
