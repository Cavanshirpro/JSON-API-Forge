# Bounded raw-deflate decoder

`puff.c` and `puff.h` are Mark Adler's puff 2.3, obtained unchanged from
[zlib v1.3.1](https://github.com/madler/zlib/tree/v1.3.1/contrib/puff).
Their copyright and permissive zlib-style terms are in `puff.h`.
They are third-party code, separately licensed from JSON API Forge.

The Editor calls `puff` with a non-null, fixed-size output buffer. It never
uses scanning mode or retries by expanding the buffer. ZIP parsing, size,
path, CRC, manifest and install policies remain first-party code. No zlib
DLL, private Qt ZIP API, or network dependency is needed to build this decoder.

Upstream Git blob IDs (SHA-1 object identity):

- `puff.c`: `d759825ab1d79fc67b453944931f87d14b6f591e`
- `puff.h`: `e23a2454316cfa0c05e5e01cd6e1d548b4f2d44e`

The source package's `MANIFEST.sha256` covers both files. Before updating,
review upstream changes and rerun the adversarial ZIP and sanitizer tests.
