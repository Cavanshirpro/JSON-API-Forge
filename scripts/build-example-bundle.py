#!/usr/bin/env python3
"""Create the deterministic, copy-ready exampleApps release ZIP."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILES = 10_000
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def _source_date_epoch() -> int:
    configured = os.environ.get("SOURCE_DATE_EPOCH")
    if configured:
        return int(configured)
    try:
        return int(
            subprocess.check_output(
                ["git", "log", "-1", "--pretty=%ct"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return 315_532_800


def _sources() -> list[tuple[Path, str]]:
    app_entries = list((ROOT / "app").rglob("*"))
    linked = [path for path in app_entries if path.is_symlink()]
    if linked:
        raise RuntimeError(f"bundle source contains symlinks: {linked}")
    paths = [path for path in app_entries if path.is_file()]
    paths.extend(
        [
            ROOT / "EXAMPLE_APPS.md",
            ROOT / "scripts/install-example.sh",
            ROOT / "scripts/install-example.ps1",
        ]
    )
    if len(paths) > MAX_FILES:
        raise RuntimeError(f"bundle file count exceeds {MAX_FILES}")

    result: list[tuple[Path, str]] = []
    total = 0
    for path in paths:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                f"bundle source must be a regular non-symlink file: {path}"
            )
        total += metadata.st_size
        if total > MAX_TOTAL_BYTES:
            raise RuntimeError(f"bundle content exceeds {MAX_TOTAL_BYTES} bytes")
        result.append((path, path.relative_to(ROOT).as_posix()))
    return sorted(result, key=lambda item: item[1])


def build(output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = _sources()
    timestamp = datetime.fromtimestamp(
        max(_source_date_epoch(), 315_532_800), tz=UTC
    ).timetuple()[:6]
    checksums: list[str] = []

    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path, name in sources:
                content = path.read_bytes()
                checksums.append(f"{hashlib.sha256(content).hexdigest()}  {name}")
                info = zipfile.ZipInfo(name, timestamp)
                info.create_system = 3
                mode = (
                    0o100755
                    if name == "scripts/install-example.sh" or os.access(path, os.X_OK)
                    else 0o100644
                )
                info.external_attr = mode << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content, compresslevel=9)

            checksum_content = ("\n".join(checksums) + "\n").encode()
            info = zipfile.ZipInfo("SHA256SUMS", timestamp)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, checksum_content, compresslevel=9)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Wrote {output} with {len(sources)} source files")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
