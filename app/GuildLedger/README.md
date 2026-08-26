# GuildLedger

Discord/community economy reference with account CRUD, immutable ledger reads, cached balance lookup and atomic idempotent transfers. Create accounts before transferring. Every transfer requires `Idempotency-Key`.

After `forge init`, use `GUILD_LEDGER_BOOTSTRAP_ADMIN_KEY` once to create a `guild_bot` API key. API prefix: `/api/guild-ledger/v1`.
