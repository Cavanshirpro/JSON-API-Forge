# Release Checklist

This checklist is for Cavanşir Qurbanzadə (`@Cavanshirpro`) and future authorized maintainers of the canonical repository.

- [ ] Confirm `VERSION` matches the intended tag.
- [ ] Review `CHANGELOG.md` and `RELEASE.md`.
- [ ] Run the documented validation/test commands.
- [ ] Confirm `.env`, credentials, database files, logs, caches, local media, `.pytest_cache`, and `__pycache__` are absent from the release tree.
- [ ] Confirm `LICENSE`, `NOTICE.md`, `LICENSE-FAQ.md`, `OWNERSHIP.md`, `AUTHORS.md`, and contributor documents are present.
- [ ] Review dependency changes and security alerts.
- [ ] Confirm documentation examples contain placeholder credentials only.
- [ ] Confirm canonical repository links and current owner/successor details are accurate.
- [ ] Confirm `MANIFEST.sha256` was regenerated after all file changes.
- [ ] Create an annotated Git tag `vX.Y.Z` from the intended commit.
- [ ] Push the tag to the canonical repository.
- [ ] Publish the GitHub Release from that tag using `RELEASE.md` as the release body.
- [ ] For source-only releases, rely on GitHub's automatic source ZIP/tar.gz unless an extra official artifact provides real value.
- [ ] If attaching a custom archive/binary, attach a checksum and preferably a signature/attestation.
- [ ] Attach only artifacts published by the Project Owner or an authorized lawful successor as Official Releases.
- [ ] Verify the release page and source tree display the source-available license notice.
