# Publishing JSON API Forge release history to GitHub

**Owner:** Cavanşir Qurbanzadə (`@Cavanshirpro`)  
**Recommended canonical repository:** `https://github.com/Cavanshirpro/JSON-API-Forge`

The recommended history is **one canonical repository with sequential release commits/tags**, not unrelated repositories. GitHub-ready ZIP files are working-tree snapshots to be committed one after another while preserving the same `.git` history.

> If you choose a different repository name, update the canonical repository references in the legal/project files before the first public release.

## 0. Create the empty repository

On GitHub, create an empty public repository named `JSON-API-Forge` under `Cavanshirpro`. Do not initialize it with another README, license, or `.gitignore`, because the v0.1.0 archive already contains those files.

## 1. Publish v0.1.0

Extract the **v0.1.0 GitHub-ready ZIP** into a clean directory and run:

```bash
git init
git config user.name "Cavanşir Qurbanzadə"
# Configure user.email separately with the email you want GitHub commits to use.

git add .
git commit -m "Release v0.1.0"
git branch -M main
git remote add origin https://github.com/Cavanshirpro/JSON-API-Forge.git
git push -u origin main

git tag -a v0.1.0 -m "JSON API Forge v0.1.0"
git push origin v0.1.0
```

Then on GitHub:

1. Open **Releases** → **Draft a new release**.
2. Choose tag `v0.1.0`.
3. Release title: `JSON API Forge v0.1.0`.
4. Paste the contents of this version's `RELEASE.md` into the description.
5. Publish the release.

GitHub automatically adds source-code ZIP and tar.gz downloads for the tag. See `RELEASE_ASSETS.md`.

## 2. Advance the same repository to v0.2.0

**Keep the existing `.git` directory.** Extract v0.2.0 elsewhere, then replace the repository working-tree files with the v0.2.0 snapshot while preserving `.git`.

After replacement:

```bash
git status
git add -A
git commit -m "Release v0.2.0"
git push origin main

git tag -a v0.2.0 -m "JSON API Forge v0.2.0"
git push origin v0.2.0
```

Create `JSON API Forge v0.2.0` in GitHub Releases using tag `v0.2.0` and that version's `RELEASE.md`.

## 3. Advance to v0.3.0

Repeat the same working-tree replacement using the v0.3.0 snapshot, again preserving `.git`:

```bash
git status
git add -A
git commit -m "Release v0.3.0"
git push origin main

git tag -a v0.3.0 -m "JSON API Forge v0.3.0"
git push origin v0.3.0
```

Create `JSON API Forge v0.3.0` in GitHub Releases using tag `v0.3.0` and the v0.3.0 `RELEASE.md`.


## 4. Advance to v0.4.0

Preserve the same `.git` directory and replace only the working tree with the v0.4.0 GitHub-ready snapshot. Then run:

```bash
git status
git add -A
git commit -m "Release v0.4.0"
git push origin main
```

**Do not tag immediately if the `main` CI run is red.** v0.4.0 adds a release gate specifically to prevent a repeat of publishing a release commit with failing required checks. After the commit CI is green:

```bash
git tag -a v0.4.0 -m "JSON API Forge v0.4.0"
git push origin v0.4.0
```

Wait for the tag workflow/release gate to pass. Then create `JSON API Forge v0.4.0` in GitHub Releases using this version's `RELEASE.md`. v0.4.0 becomes the current `main` state.

## 5. Do not make release ZIPs independent Git histories

The intended history is:

```text
main
 ├── commit: Release v0.1.0  ← tag v0.1.0
 ├── commit: Release v0.2.0  ← tag v0.2.0
 ├── commit: Release v0.3.0  ← tag v0.3.0
 └── commit: Release v0.4.0  ← tag v0.4.0
```

This gives GitHub meaningful comparisons and changelogs between releases.

## 6. Recommended repository settings

After the first push:

- enable the dependency graph and Dependabot alerts;
- enable Private Vulnerability Reporting/Security Advisories if available;
- enable secret scanning and push protection when available;
- protect `main` after the initial release sequence is complete;
- require pull requests and passing CI for external changes;
- keep Actions permissions as restrictive as practical;
- consider signed commits/tags for future official releases;
- keep the repository public only if you accept that GitHub users can view and technically fork a public repository under GitHub's platform rules.

`.github/CODEOWNERS` assigns default review ownership to `@Cavanshirpro`. `.github/release.yml` configures categorized automatically generated notes for future PR-driven releases.

## 7. License presentation

The license is custom/source-available, so GitHub may identify it as **Other** instead of a standard SPDX/OSI license. This is expected. Do not describe JSON API Forge as OSI open source; describe it as **source-available**.

The current legal/project owner is Cavanşir Qurbanzadə. `OWNERSHIP.md` explains the intended path for a later transfer to a company.
