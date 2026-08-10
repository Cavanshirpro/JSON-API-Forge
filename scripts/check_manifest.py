#!/usr/bin/env python3
from __future__ import annotations
import hashlib, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; MANIFEST=ROOT/"MANIFEST.sha256"
def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def release_files()->set[str]:
    try:
        raw=subprocess.check_output(["git","ls-files","-z"],cwd=ROOT,stderr=subprocess.DEVNULL).decode()
        return {x for x in raw.split("\0") if x and x!="MANIFEST.sha256" and not x.startswith(".git/")}
    except Exception:
        ignored={"MANIFEST.sha256"}
        out=set()
        for p in ROOT.rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(ROOT).as_posix()
            if rel in ignored or any(part in {"__pycache__",".pytest_cache",".ruff_cache",".mypy_cache","dist","build",".git"} for part in p.relative_to(ROOT).parts):continue
            if rel.endswith((".pyc",".pyo")) or rel.startswith("data/") or rel.startswith("media/") or rel.startswith("logs/"):continue
            out.add(rel)
        return out
def main()->int:
    if not MANIFEST.exists():raise SystemExit("MANIFEST.sha256 is missing")
    expected={}
    for n,line in enumerate(MANIFEST.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():continue
        try:d,rel=line.split("  ",1)
        except ValueError:raise SystemExit(f"Malformed manifest line {n}")
        if rel in expected:raise SystemExit(f"Duplicate manifest entry: {rel}")
        expected[rel]=d
    actual=release_files(); errors=[]
    for rel,d in expected.items():
        p=ROOT/rel
        if not p.is_file():errors.append(f"missing: {rel}")
        elif digest(p)!=d:errors.append(f"hash mismatch: {rel}")
    for rel in sorted(actual-set(expected)):errors.append(f"release file not in manifest: {rel}")
    for rel in sorted(set(expected)-actual):errors.append(f"manifest-only file: {rel}")
    if errors:raise SystemExit("MANIFEST verification failed:\n- " + "\n- ".join(errors))
    print(f"MANIFEST verified: {len(expected)} files"); return 0
if __name__=="__main__":raise SystemExit(main())
