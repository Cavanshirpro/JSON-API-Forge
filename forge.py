from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from framework.config import load_config
from framework.domain import expand_feature_packs

ROOT = Path(__file__).resolve().parent


def cmd_validate(_: argparse.Namespace) -> None:
    cfg = load_config(ROOT / "app")
    for p in cfg.projects:
        expand_feature_packs(p)
    print(f"OK: {len(cfg.projects)} project(s)")
    for p in cfg.projects:
        print(f"  {p.slug}: resources={len(p.resources)} operations={len(p.operations)} data_sources={len(p.data_sources)} events={len(p.event_channels)}")


def cmd_routes(_: argparse.Namespace) -> None:
    from framework.factory import create_app
    app = create_app()
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path: continue
        methods = ",".join(sorted(getattr(route, "methods", []) or ["WS"]))
        print(f"{methods:18} {path}")


def cmd_new_app(args: argparse.Namespace) -> None:
    name = args.name
    slug = args.slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    target = ROOT / "app" / name
    if target.exists(): raise SystemExit(f"Already exists: {target}")
    (target / "config").mkdir(parents=True)
    (target / "hooks").mkdir()
    (target / "data").mkdir()
    env_prefix = slug.upper().replace("-", "_")
    manifest = {
        "$schema": "../../schemas/fragment.schema.json",
        "slug": slug,
        "name": name,
        "version": "1.0.0",
        "api_prefix": f"/api/{slug}/v1",
        "docs_enabled": True,
        "audit_enabled": True,
    }
    fragments = {
        "10-databases.json": {
            "$schema": "../../../schemas/fragment.schema.json",
            "databases": {"primary": {"url": f"$env:{env_prefix}_DATABASE_URL:-sqlite+aiosqlite:///./data/{slug}.db"}},
        },
        "20-security.json": {
            "$schema": "../../../schemas/fragment.schema.json",
            "security": {"bootstrap_admin_key": f"$env:{env_prefix}_BOOTSTRAP_ADMIN_KEY"},
            "roles": {"admin": {"permissions": ["*"]}},
        },
        "30-performance.json": {
            "$schema": "../../../schemas/fragment.schema.json",
            "cache": {"enabled": True, "backend": "memory", "default_ttl_seconds": 30},
            "rate_limit": {"enabled": True, "backend": "memory", "requests": 300, "window_seconds": 60},
        },
        "40-resources.json": {
            "$schema": "../../../schemas/fragment.schema.json",
            "resources": [], "operations": [], "data_sources": [],
        },
    }
    (target / "app.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for filename, value in fragments.items():
        (target / "config" / filename).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    (target / "hooks" / "__init__.py").write_text("", encoding="utf-8")
    print(f"Created {target} with app.json + {len(fragments)} config fragments")


def main() -> None:
    parser = argparse.ArgumentParser(prog="forge", description="JSON API Forge developer CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate"); p.set_defaults(func=cmd_validate)
    p = sub.add_parser("routes"); p.set_defaults(func=cmd_routes)
    p = sub.add_parser("new-app"); p.add_argument("name"); p.add_argument("--slug"); p.set_defaults(func=cmd_new_app)
    args = parser.parse_args(); args.func(args)


if __name__ == "__main__":
    main()
