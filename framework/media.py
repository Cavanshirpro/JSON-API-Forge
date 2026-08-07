from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, insert, select

from .config import MediaConfig
from .security import media_table
from .settings import settings

_SAFE = __import__('re').compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    name = Path(name or "file").name
    cleaned = _SAFE.sub("_", name).strip("._")
    return (cleaned or "file")[:180]


def _extension(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


class LocalMediaStore:
    def __init__(self, root: str):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, storage_key: str) -> Path:
        p = (self.root / storage_key).resolve()
        if self.root not in p.parents and p != self.root: raise HTTPException(status_code=400, detail="Invalid media path")
        return p

    async def save_upload(self, upload: UploadFile, storage_key: str, max_bytes: int) -> tuple[int, str]:
        path = self.path_for(storage_key); path.parent.mkdir(parents=True, exist_ok=True)
        total, digest = 0, hashlib.sha256()
        try:
            with path.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk: break
                    total += len(chunk)
                    if total > max_bytes: raise HTTPException(status_code=413, detail="Media file exceeds configured maximum size")
                    digest.update(chunk); out.write(chunk)
        except Exception:
            path.unlink(missing_ok=True); raise
        finally:
            await upload.close()
        return total, digest.hexdigest()

    def delete(self, storage_key: str) -> None: self.path_for(storage_key).unlink(missing_ok=True)


def build_media_store(config: MediaConfig):
    if config.backend == "local": return LocalMediaStore(config.local_directory)
    raise RuntimeError("S3 media backend is configured but this build does not silently emulate it. Add a production S3 adapter before selecting backend='s3'.")


async def _enforce_owner_quota(engine, project_slug: str, owner_subject: str, config: MediaConfig) -> None:
    if not config.max_owner_bytes: return
    async with engine.connect() as conn:
        used = (await conn.execute(select(func.coalesce(func.sum(media_table.c.size), 0)).where(
            (media_table.c.project_slug == project_slug) & (media_table.c.owner_subject == owner_subject[:160])
        ))).scalar_one()
    if int(used) >= config.max_owner_bytes:
        raise HTTPException(status_code=413, detail="Media owner quota exceeded")


async def save_media(*, engine, store: LocalMediaStore, project_slug: str, config: MediaConfig, upload: UploadFile, owner_subject: str):
    content_type = (upload.content_type or "application/octet-stream").lower()
    if config.allowed_mime_types and content_type not in config.allowed_mime_types:
        raise HTTPException(status_code=415, detail=f"Media type not allowed: {content_type}")
    safe = _safe_name(upload.filename or "file")
    ext = _extension(safe)
    if config.allowed_extensions and ext not in {x.lower().lstrip('.') for x in config.allowed_extensions}:
        raise HTTPException(status_code=415, detail=f"File extension not allowed: {ext or '(none)'}")
    await _enforce_owner_quota(engine, project_slug, owner_subject, config)

    media_id = secrets.token_hex(16)
    storage_key = f"{project_slug}/{datetime.now(timezone.utc):%Y/%m}/{media_id}-{safe}"
    size, digest = await store.save_upload(upload, storage_key, config.max_upload_bytes)

    if config.max_owner_bytes:
        # Recheck using exact uploaded size. This is a soft quota under races; strict quotas need a transactional quota ledger.
        async with engine.connect() as conn:
            used = (await conn.execute(select(func.coalesce(func.sum(media_table.c.size), 0)).where(
                (media_table.c.project_slug == project_slug) & (media_table.c.owner_subject == owner_subject[:160])
            ))).scalar_one()
        if int(used) + size > config.max_owner_bytes:
            store.delete(storage_key); raise HTTPException(status_code=413, detail="Media upload would exceed owner quota")

    if config.deduplicate:
        async with engine.connect() as conn:
            existing = (await conn.execute(select(media_table).where(
                (media_table.c.project_slug == project_slug) & (media_table.c.sha256 == digest)
            ))).mappings().first()
        if existing:
            store.delete(storage_key); return dict(existing)

    values = {
        "id": media_id, "project_slug": project_slug, "storage_key": storage_key,
        "original_name": safe, "content_type": content_type, "size": size, "sha256": digest,
        "owner_subject": owner_subject[:160], "created_at": datetime.now(timezone.utc),
    }
    async with engine.begin() as conn: await conn.execute(insert(media_table).values(**values))
    return values


async def get_media_meta(engine, project_slug: str, media_id: str):
    async with engine.connect() as conn:
        row = (await conn.execute(select(media_table).where((media_table.c.id == media_id) & (media_table.c.project_slug == project_slug)))).mappings().first()
    if not row: raise HTTPException(status_code=404, detail="Media not found")
    return dict(row)


async def delete_media(engine, store: LocalMediaStore, project_slug: str, media_id: str):
    row = await get_media_meta(engine, project_slug, media_id); store.delete(row["storage_key"])
    async with engine.begin() as conn:
        await conn.execute(delete(media_table).where((media_table.c.id == media_id) & (media_table.c.project_slug == project_slug)))
    return True


def make_signed_media_token(project_slug: str, media_id: str, ttl_seconds: int) -> str:
    if not settings.jwt_secret: raise RuntimeError("JWT_SECRET is required for signed media URLs")
    expires = int(time.time()) + ttl_seconds
    message = f"{project_slug}:{media_id}:{expires}".encode()
    sig = hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{expires}.{encoded}"


def verify_signed_media_token(project_slug: str, media_id: str, token: str | None) -> bool:
    if not token or not settings.jwt_secret: return False
    try:
        exp_raw, supplied = token.split(".", 1); expires = int(exp_raw)
    except (ValueError, TypeError): return False
    if expires < int(time.time()): return False
    message = f"{project_slug}:{media_id}:{expires}".encode()
    expected = base64.urlsafe_b64encode(hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).digest()).rstrip(b"=").decode()
    return hmac.compare_digest(supplied, expected)
