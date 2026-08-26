from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import case, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from .config import MediaConfig
from .security import media_table, media_usage_table

log = logging.getLogger("json_api_forge.media")
_SAFE = __import__("re").compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    name = Path(name or "file").name
    cleaned = _SAFE.sub("_", name).strip("._")
    return (cleaned or "file")[:180]


def _extension(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


class LocalMediaStore:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if self.root not in path.parents and path != self.root:
            raise HTTPException(status_code=400, detail="Invalid media path")
        return path

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
    return LocalMediaStore(config.local_directory)


async def _ensure_usage_row(engine, project_slug: str, owner_subject: str) -> None:
    owner = owner_subject[:160]
    async with engine.connect() as conn:
        exists = (
            await conn.execute(
                select(media_usage_table.c.used_bytes).where(
                    (media_usage_table.c.project_slug == project_slug) & (media_usage_table.c.owner_subject == owner)
                )
            )
        ).first()
        if exists:
            return
        used = (
            await conn.execute(
                select(func.coalesce(func.sum(media_table.c.size), 0)).where(
                    (media_table.c.project_slug == project_slug) & (media_table.c.owner_subject == owner)
                )
            )
        ).scalar_one()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                insert(media_usage_table).values(
                    project_slug=project_slug, owner_subject=owner, used_bytes=int(used), updated_at=datetime.now(UTC)
                )
            )
    except IntegrityError:
        return


async def _reserve_usage(conn, project_slug: str, owner_subject: str, size: int, limit: int) -> None:
    owner = owner_subject[:160]
    result = await conn.execute(
        update(media_usage_table)
        .where(
            (media_usage_table.c.project_slug == project_slug)
            & (media_usage_table.c.owner_subject == owner)
            & (media_usage_table.c.used_bytes + size <= limit)
        )
        .values(used_bytes=media_usage_table.c.used_bytes + size, updated_at=datetime.now(UTC))
    )
    if not result.rowcount:
        raise HTTPException(status_code=413, detail="Media upload would exceed owner quota")


async def save_media(*, engine, store: LocalMediaStore, project_slug: str, config: MediaConfig, upload: UploadFile, owner_subject: str):
    content_type = (upload.content_type or "application/octet-stream").lower()
    if config.allowed_mime_types and content_type not in config.allowed_mime_types:
        raise HTTPException(status_code=415, detail=f"Media type not allowed: {content_type}")
    safe = _safe_name(upload.filename or "file")
    ext = _extension(safe)
    if config.allowed_extensions and ext not in {x.lower().lstrip(".") for x in config.allowed_extensions}:
        raise HTTPException(status_code=415, detail=f"File extension not allowed: {ext or '(none)'}")
    media_id = secrets.token_hex(16)
    storage_key = f"{project_slug}/{datetime.now(UTC):%Y/%m}/{media_id}-{safe}"
    size, digest = await store.save_upload(upload, storage_key, config.max_upload_bytes)
    if config.deduplicate:
        filt = (media_table.c.project_slug == project_slug) & (media_table.c.sha256 == digest)
        if config.deduplicate_scope == "owner":
            filt = filt & (media_table.c.owner_subject == owner_subject[:160])
        async with engine.connect() as conn:
            existing = (await conn.execute(select(media_table).where(filt))).mappings().first()
        if existing:
            store.delete(storage_key)
            return dict(existing)
    values = {
        "id": media_id,
        "project_slug": project_slug,
        "storage_key": storage_key,
        "original_name": safe,
        "content_type": content_type,
        "size": size,
        "sha256": digest,
        "owner_subject": owner_subject[:160],
        "created_at": datetime.now(UTC),
    }
    if config.max_owner_bytes:
        await _ensure_usage_row(engine, project_slug, owner_subject)
    try:
        async with engine.begin() as conn:
            if config.max_owner_bytes:
                await _reserve_usage(conn, project_slug, owner_subject, size, config.max_owner_bytes)
            await conn.execute(insert(media_table).values(**values))
    except Exception:
        store.delete(storage_key)
        raise
    return values


def media_api_meta(meta: dict, *, include_owner: bool = False) -> dict:
    result = {field: meta.get(field) for field in ("id", "original_name", "content_type", "size", "sha256", "created_at")}
    if include_owner:
        result["owner_subject"] = meta.get("owner_subject")
    return result


async def get_media_meta(engine, project_slug: str, media_id: str):
    async with engine.connect() as conn:
        row = (
            (await conn.execute(select(media_table).where((media_table.c.id == media_id) & (media_table.c.project_slug == project_slug))))
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    return dict(row)


async def delete_media(engine, store: LocalMediaStore, project_slug: str, media_id: str):
    row = await get_media_meta(engine, project_slug, media_id)
    async with engine.begin() as conn:
        result = await conn.execute(
            delete(media_table).where((media_table.c.id == media_id) & (media_table.c.project_slug == project_slug))
        )
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Media not found")
        await conn.execute(
            update(media_usage_table)
            .where((media_usage_table.c.project_slug == project_slug) & (media_usage_table.c.owner_subject == row["owner_subject"]))
            .values(
                used_bytes=case((media_usage_table.c.used_bytes >= row["size"], media_usage_table.c.used_bytes - row["size"]), else_=0),
                updated_at=datetime.now(UTC),
            )
        )
    try:
        store.delete(row["storage_key"])
    except Exception:
        log.exception("Media metadata deleted but local object cleanup failed media_id=%s", media_id)
    return True


def make_signed_media_token(project_slug: str, media_id: str, ttl_seconds: int, *, secret: str) -> str:
    if not secret:
        raise RuntimeError("A media signing secret is required for signed media URLs")
    expires = int(time.time()) + ttl_seconds
    message = f"{project_slug}:{media_id}:{expires}".encode()
    signature = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{expires}.{encoded}"


def verify_signed_media_token(project_slug: str, media_id: str, token: str | None, *, secret: str) -> bool:
    if not token or not secret:
        return False
    try:
        exp_raw, supplied = token.split(".", 1)
        expires = int(exp_raw)
    except (ValueError, TypeError):
        return False
    if expires < int(time.time()):
        return False
    message = f"{project_slug}:{media_id}:{expires}".encode()
    expected = base64.urlsafe_b64encode(hmac.new(secret.encode(), message, hashlib.sha256).digest()).rstrip(b"=").decode()
    return hmac.compare_digest(supplied, expected)
