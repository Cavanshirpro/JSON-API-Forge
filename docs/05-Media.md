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
    "owner_delete_only": true
  }
}
```

## Signed URLs

A client with `media.read` can request a temporary signed path. The download route verifies project, media ID and expiry with HMAC. The token does not grant access to another media ID.

Rotate `JWT_SECRET` carefully: current signed URLs become invalid, which is usually desirable during a credential rotation.

## Storage quota note

The built-in owner quota is a practical soft quota. Under highly concurrent uploads, strict quota accounting requires a transactional reservation/ledger instead of only summing metadata.

## Object storage boundary

The config model retains `backend:"s3"`, but this build intentionally refuses to pretend local disk is S3. A real production S3-compatible adapter should implement multipart upload, signed object/CDN URLs and lifecycle rules.

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
