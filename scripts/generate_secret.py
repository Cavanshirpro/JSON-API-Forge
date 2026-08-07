import secrets

print("BOOTSTRAP_ADMIN_KEY=" + secrets.token_urlsafe(48))
print("JWT_SECRET=" + secrets.token_urlsafe(64))
