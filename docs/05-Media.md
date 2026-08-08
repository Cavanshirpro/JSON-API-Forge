# Media subsystem

## Implemented local-storage capabilities

- `UploadFile` multipart uploads;
- chunked copy to disk rather than intentionally loading the whole object into RAM;
- per-file byte limit;
- batch upload count limit;
- MIME allowlist;
- optional extension allowlist;
- safe filenames and random media IDs;
- SHA-256 content digest;
- optional deduplication;
- optional per-owner storage quota;
- metadata in Forge's internal DB;
- private/public read policy;
- upload/read/delete/admin permissions;
- optional owner-only delete policy;
- HMAC-signed temporary media URLs;
- optional post-upload Python hooks for queues/scanners/transcoding dispatch;
- `FileResponse` download behavior, including the underlying Starlette file-serving features supported by the installed version.

Routes include:

```text
POST   <prefix>/media
POST   <prefix>/media/_batch
GET    <prefix>/media/{id}
GET    <prefix>/media/{id}/meta
POST   <prefix>/media/{id}/signed-url
DELETE <prefix>/media/{id}
```

## Example

```json
{
  "media": {
    "enabled": true,
    "backend": "local",
    "local_directory": "./data/media-app1",
    "max_upload_bytes": 26214400,
    "max_batch_files": 8,
    "max_owner_bytes": 524288000,
    "allowed_mime_types": ["image/jpeg", "image/png", "video/mp4"],
    "allowed_extensions": ["jpg", "jpeg", "png", "mp4"],
    "public": false,
    "signed_urls_enabled": true,
    "signed_url_ttl_seconds": 300,
    "owner_delete_only": true,
    "deduplicate": true,
    "deduplicate_scope": "owner"
  }
}
```

## Signed URLs

A client with `media.read` can request a temporary signed path. The download route verifies project, media ID and expiry with HMAC. The token does not grant access to another media ID.

Rotate `JWT_SECRET` carefully: current signed URLs become invalid, which is usually desirable during a credential rotation.

## Storage quota note

The built-in owner quota is a practical soft quota. Under highly concurrent uploads, strict quota accounting requires a transactional reservation/ledger instead of only summing metadata.

## Object storage boundary

v0.4 exposes only `backend:"local"`. It intentionally does not advertise an unimplemented S3-compatible adapter as valid configuration. A future object-storage adapter must ship with a real implementation, tests, multipart/streaming policy, signed object/CDN URL behavior and lifecycle rules before becoming a valid backend value.

Recommended heavy-media pipeline:

```text
upload → type/size validation → object storage
                                ↓
                         durable job queue
                                ↓
                 malware scan / thumbnails / transcode
                                ↓
                              CDN
```

Do not transcode large videos synchronously in an API request.

## Metadata boundary and deduplication privacy

The database record contains internal fields needed by the runtime, including the physical `storage_key` and `owner_subject`. These are **not** returned wholesale to normal API callers. Public API metadata is reduced to client-safe fields such as media ID, original name, content type, byte size, SHA-256 digest and creation time. `storage_key` is never part of the normal media DTO. Owner identity is exposed only when the requester is the owner or holds `media.admin`.

Deduplication defaults to:

```json
{"deduplicate_scope":"owner"}
```

This prevents user A from uploading bytes that already belong to user B and learning/reusing user B's metadata record as a side effect. `project` scope is available for deployments that deliberately treat matching content as one project-wide object and have reviewed that privacy implication.

If a file is successfully streamed to local storage but the metadata transaction fails, Forge removes the newly written file before surfacing the error. This avoids ordinary metadata-insert failures leaving silent orphan files. Operational cleanup/backup policy is still required for crashes, manual filesystem changes and external storage failures.

## Validation boundary

`UploadFile.content_type` and filename extensions are policy signals supplied around the upload; an allow-list is **not malware scanning or authoritative content inspection**. Security-sensitive deployments should add magic-byte/content inspection, antivirus/malware scanning and image/video decoding in a durable post-upload pipeline before publishing untrusted content.
