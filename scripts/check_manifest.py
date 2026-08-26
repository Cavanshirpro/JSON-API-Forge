#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def release_files() -> set[str]:
    try:
        raw = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        ).decode()
        return {
            x
            for x in raw.split("\0")
            if x and x != "MANIFEST.sha256" and not x.startswith(".git/")
        }
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        ignored = {"MANIFEST.sha256"}
        out = set()
        for p in ROOT.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if rel in ignored or any(
                part
                in {
                    "__pycache__",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".mypy_cache",
                    "dist",
                    "build",
                    ".git",
                }
                for part in p.relative_to(ROOT).parts
            ):
                continue
            if rel.endswith((".pyc", ".pyo")) or rel.startswith(
                ("data/", "media/", "logs/")
            ):
                continue
            out.add(rel)
        return out


def write_manifest() -> None:
    entries = [
        f"{digest(ROOT / relative)}  {relative}" for relative in sorted(release_files())
    ]
    MANIFEST.write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(f"MANIFEST written: {len(entries)} files")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify or regenerate the tracked release-file SHA-256 manifest"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate MANIFEST.sha256 from release files",
    )
    args = parser.parse_args(argv)
    if args.write:
        write_manifest()
        return 0
    if not MANIFEST.exists():
        raise SystemExit("MANIFEST.sha256 is missing")
    expected = {}
    for n, line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            d, rel = line.split("  ", 1)
        except ValueError as exc:
            raise SystemExit(f"Malformed manifest line {n}") from exc
        if rel in expected:
            raise SystemExit(f"Duplicate manifest entry: {rel}")
        expected[rel] = d
    actual = release_files()
    errors = []
    for rel, d in expected.items():
        p = ROOT / rel
        if not p.is_file():
            errors.append(f"missing: {rel}")
        elif digest(p) != d:
            errors.append(f"hash mismatch: {rel}")
    for rel in sorted(actual - set(expected)):
        errors.append(f"release file not in manifest: {rel}")
    for rel in sorted(set(expected) - actual):
        errors.append(f"manifest-only file: {rel}")
    if errors:
        raise SystemExit("MANIFEST verification failed:\n- " + "\n- ".join(errors))
    print(f"MANIFEST verified: {len(expected)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
