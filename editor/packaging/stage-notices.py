#!/usr/bin/env python3
"""Preserve available dependency notices from the selected Qt kit and OS packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def query_qt() -> tuple[Path, str]:
    for name in ("qtpaths6", "qtpaths", "qmake6", "qmake"):
        executable = shutil.which(name)
        if executable is None:
            continue
        option = "-query" if name.startswith("qmake") else "--query"
        try:
            prefix = subprocess.check_output(
                [executable, option, "QT_INSTALL_PREFIX"], text=True, timeout=15
            ).strip()
            version = subprocess.check_output(
                [executable, option, "QT_VERSION"], text=True, timeout=15
            ).strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if Path(prefix).is_dir() and re.fullmatch(r"6\.\d+\.\d+", version):
            return Path(prefix), version
    raise RuntimeError("Put the matching Qt kit's qtpaths or qmake on PATH")


def stage_notices(stage: Path) -> None:
    stage = stage.resolve(strict=True)
    if not stage.is_dir() or stage == ROOT:
        raise ValueError("Use a staged install directory, not the source root")
    prefix, version = query_qt()
    destination = stage / "licenses" / "dependencies"
    destination.mkdir(parents=True, exist_ok=True)
    records = []

    def preserve(source: Path, relative: Path) -> None:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        records.append(
            {
                "file": relative.as_posix(),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )

    # Copy the selected kit's own records; do not invent a deployment SBOM from
    # these broader kit inventories. Some distro/older kits do not ship an SBOM.
    seen_directories = []
    for name in ("sbom", "licenses", "Licenses", "LICENSES"):
        directory = prefix / name
        if directory.is_dir():
            if any(directory.samefile(seen) for seen in seen_directories):
                continue
            seen_directories.append(directory)
            for source in sorted(directory.rglob("*")):
                if source.is_file():
                    preserve(
                        source, Path("qt-kit") / name / source.relative_to(directory)
                    )

    packages = []
    dpkg = shutil.which("dpkg-query")
    if dpkg:
        result = subprocess.run(
            [
                dpkg,
                "-W",
                "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n",
                "libqt6*",
                "qt6-*",
            ],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        for line in sorted(result.stdout.splitlines()):
            values = line.split("\t")
            if len(values) != 4 or not values[1]:
                continue
            package, package_version, source_package, source_version = values
            name = package.split(":", 1)[0]
            if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name):
                continue
            notice = Path("/usr/share/doc") / name / "copyright"
            if notice.is_file():
                preserve(notice, Path("ubuntu") / name / "copyright")
            packages.append(
                {
                    "name": package,
                    "version": package_version,
                    "source_package": source_package,
                    "source_version": source_version,
                }
            )

    inventory = {
        "schema_version": 1,
        "qt_version": version,
        "scope": "Available selected-kit records and installed Qt package notices; not a complete deployed SBOM.",
        "qt_packages": packages,
        "files": sorted(records, key=lambda record: record["file"]),
        "review": "Review actual native runtime, WebEngine/Chromium and IFW source/notices before distribution. See THIRD_PARTY_NOTICES.md.",
    }
    (destination / "inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Qt {version}: staged {len(records)} dependency notice/SBOM files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    stage_notices(parser.parse_args().stage)
