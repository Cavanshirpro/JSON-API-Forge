# Media Consistency, Quotas, and Batch Semantics

v0.4 supports the **local filesystem media backend**. It intentionally does not advertise an unimplemented S3 backend as valid configuration.

## 1. Storage scope

```json
{
  "media": {
    "enabled": true,
    "backend": "local",
    "local_directory": "./data/media"
  }
}
```

Local disk is appropriate when one deployment node owns the files and backup/redeploy behavior is understood. It is not shared object storage for arbitrary horizontal scaling.

## 2. Streaming upload limits

Uploads are streamed with a configured maximum size rather than requiring the whole file in application memory.

MIME/extension allowlists are policy checks, not malware scanning or content authenticity verification.

## 3. Safe metadata boundary

API metadata omits internal storage path/key details. Internal filesystem identifiers are implementation details and should not become a client contract.

## 4. Deduplication

Deduplication can use file hashes. Owner-scoped dedup is the safe default because project-wide dedup can reveal that another user already uploaded the same secret file or return another owner's metadata.

## 5. Owner quota

When `max_owner_bytes` is configured, v0.4 tracks owner usage in an internal ledger and performs authoritative reservation/update transactionally with metadata persistence. This avoids a simple `SUM()` pre-check race where two workers both see free quota and commit beyond the limit.

## 6. Failure cleanup

If filesystem write succeeds but metadata transaction fails, Forge attempts to clean up the orphaned file. Deletion is designed around keeping database/API state authoritative and using best-effort filesystem cleanup where a cross-resource transaction is impossible.

## 7. Signed URLs

Signed URLs require an explicit `media.signing_secret`; they are not implicitly coupled to the project's JWT secret.

```json
{
  "signed_urls_enabled": true,
  "signing_secret": "$env:APP1_MEDIA_SIGNING_SECRET",
  "signed_url_ttl_seconds": 300
}
```

Rotating this secret invalidates outstanding signatures.

## 8. Batch upload semantics

Batch upload is **partial-result**, not an all-files distributed transaction. Each file has an explicit success/failure result. If file 3 fails after files 1 and 2 have committed, the API does not pretend the first two never happened.

Clients should inspect every item result and decide whether to retry failed files or compensate successful ones.

## 9. Horizontal scale

Before multi-host media scale, add a real shared object-storage adapter with its own implementation/tests or terminate uploads at another storage service. Do not mount “S3” configuration copied from an older document; v0.4 accepts only implemented backends.
