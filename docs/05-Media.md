# Media subsystem

Enable media per project. The implemented local backend provides:

- streamed multipart upload (does not read the whole file into RAM)
- maximum upload size
- MIME allowlist
- path-safe filenames
- random object IDs
- SHA-256 digest
- optional content deduplication
- metadata stored in the Forge internal DB
- upload/read/delete permissions
- private or public read mode
- file download with correct content type

Routes:

```text
POST   <prefix>/media
GET    <prefix>/media/{id}
GET    <prefix>/media/{id}/meta
DELETE <prefix>/media/{id}
```

For large production media workloads, store objects outside the web server filesystem (S3-compatible object storage, CDN) and implement the storage adapter. Image resizing, video transcoding, thumbnails and malware scanning should run in background workers, not in the request handler.

Recommended media pipeline:

```text
upload → validation → object storage → metadata DB
                           ↓
                        queue
                           ↓
            virus scan / thumbnails / transcode
                           ↓
                         CDN
```
