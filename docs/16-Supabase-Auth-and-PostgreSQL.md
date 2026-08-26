# Supabase Auth and PostgreSQL

External identity can be integrated through JWKS rather than sharing a local signing secret. Configure the JWKS URL, expected issuer/audience/algorithms and the claim paths used for subject/tenant/roles/permissions.

JWKS responses are cached with bounded TTL and refreshed once when an unknown `kid` suggests key rotation. Key metadata (`alg`, `use`, `key_ops`) is checked before verification.

Trusting authorization claims is a deliberate security boundary. Map only claims your issuer controls. A valid external identity token should not automatically become an administrator without explicit Forge role/permission trust configuration.

PostgreSQL remains a separate resource authorization boundary; tenant/owner constraints should also be applied at CRUD/RPC level rather than assuming the identity provider alone isolates rows.
