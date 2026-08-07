from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, insert, select

from .config import MediaConfig
from .security import media_table

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    name = Path(name or "file").name
    cleaned = _SAFE.sub("_", name).strip("._")
    return (cleaned or "file")[:180]


class LocalMediaStore:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, storage_key: str) -> Path:
        p = (self.root / storage_key).resolve()
        if self.root not in p.parents and p != self.root:
            raise HTTPException(status_code=400, detail="Invalid media path")
        return p

    async def save_upload(self, upload: UploadFile, storage_key: str, max_bytes: int) -> tuple[int, str]:
        path = self.path_for(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        digest = hashlib.sha256()
        try:
            with path.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(status_code=413, detail="Media file exceeds configured maximum size")
                    digest.update(chunk)
                    out.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return total, digest.hexdigest()

    def delete(self, storage_key: str) -> None:
        self.path_for(storage_key).unlink(missing_ok=True)


def build_media_store(config: MediaConfig):
    if config.backend == "local":
        return LocalMediaStore(config.local_directory)
    raise RuntimeError("S3 media backend is configured but this build only enables the local runtime backend. Use a custom storage adapter before production S3 deployment.")


async def save_media(*, engine, store: LocalMediaStore, project_slug: str, config: MediaConfig, upload: UploadFile, owner_subject: str):
    content_type = (upload.content_type or "application/octet-stream").lower()
    if config.allowed_mime_types and content_type not in config.allowed_mime_types:
        raise HTTPException(status_code=415, detail=f"Media type not allowed: {content_type}")

    media_id = secrets.token_hex(16)
    safe = _safe_name(upload.filename or "file")
    storage_key = f"{project_slug}/{datetime.now(timezone.utc):%Y/%m}/{media_id}-{safe}"
    size, digest = await store.save_upload(upload, storage_key, config.max_upload_bytes)

    if config.deduplicate:
        async with engine.connect() as conn:
            existing = (await conn.execute(select(media_table).where(
                (media_table.c.project_slug == project_slug) & (media_table.c.sha256 == digest)
            ))).mappings().first()
        if existing:
            store.delete(storage_key)
            return dict(existing)

    values = {
        "id": media_id, "project_slug": project_slug, "storage_key": storage_key,
        "original_name": safe, "content_type": content_type, "size": size, "sha256": digest,
        "owner_subject": owner_subject[:160], "created_at": datetime.now(timezone.utc),
    }
    async with engine.begin() as conn:
        await conn.execute(insert(media_table).values(**values))
    return values


async def get_media_meta(engine, project_slug: str, media_id: str):
    async with engine.connect() as conn:
        row = (await conn.execute(select(media_table).where(
            (media_table.c.id == media_id) & (media_table.c.project_slug == project_slug)
        ))).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    return dict(row)


async def delete_media(engine, store: LocalMediaStore, project_slug: str, media_id: str):
    row = await get_media_meta(engine, project_slug, media_id)
    store.delete(row["storage_key"])
    async with engine.begin() as conn:
        await conn.execute(delete(media_table).where(
            (media_table.c.id == media_id) & (media_table.c.project_slug == project_slug)
        ))
    return True
