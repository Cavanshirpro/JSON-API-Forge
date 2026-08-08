#!/usr/bin/env python3
"""Fail CI when security, data-integrity, lifecycle, or assembly coverage regresses.

Aggregate coverage is useful, but it can hide a dangerous drop in a small module that
owns authentication, transactions, backpressure, lifecycle cleanup, or generated route
assembly. v0.4 therefore enforces per-module branch-aware coverage floors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Most data/security modules require >=80%. The generated project router has a broader
# declarative surface and a deliberately separate >=75% floor; this is still high enough
# to make route assembly a release gate instead of letting it disappear inside aggregate
# coverage. Factory/runtime orchestration remain at >=80%.
MODULE_FLOORS: dict[str, float] = {
    "framework/audit.py": 80.0,
    "framework/cache.py": 80.0,
    "framework/crud.py": 80.0,
    "framework/datasources.py": 80.0,
    "framework/db.py": 80.0,
    "framework/events.py": 80.0,
    "framework/factory.py": 80.0,
    "framework/media.py": 80.0,
    "framework/mongo.py": 80.0,
    "framework/observability.py": 80.0,
    "framework/operations.py": 80.0,
    "framework/protection.py": 80.0,
    "framework/rate_limit.py": 80.0,
    "framework/routers/project.py": 75.0,
    "framework/runtime.py": 80.0,
    "framework/security.py": 80.0,
    "framework/services/http_client.py": 80.0,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="coverage.json")
    parser.add_argument(
        "--minimum",
        type=float,
        default=None,
        help="Override every module floor with one value (mainly for local diagnostics).",
    )
    args = parser.parse_args()

    path = Path(args.report)
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload.get("files", {})
    failures: list[str] = []

    print("Critical module branch-aware coverage gates:")
    for module, configured_floor in MODULE_FLOORS.items():
        floor = args.minimum if args.minimum is not None else configured_floor
        info = files.get(module)
        if info is None:
            failures.append(f"{module}: missing from coverage report")
            continue
        percent = float(info.get("summary", {}).get("percent_covered", 0.0))
        print(f"  {module:<42} {percent:6.2f}%  required>={floor:5.1f}%")
        if percent + 1e-9 < floor:
            failures.append(f"{module}: {percent:.2f}% < {floor:.2f}%")

    if failures:
        print("\nCoverage gate failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Critical coverage gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
