# MediaLibrary

Private local-media reference with owner quota, batch/size bounds, MIME and extension allowlists, owner-scoped deduplication, plus SQL collection metadata. Signed public links stay disabled so no signing secret is silently invented.

After `forge init`, exchange `MEDIA_LIBRARY_BOOTSTRAP_ADMIN_KEY` for a `media_contributor` or `media_reader` API key. API prefix: `/api/media-library/v1`.
