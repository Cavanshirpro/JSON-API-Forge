# Discord economy bot → Forge API → PostgreSQL

This is the recommended integration model for a Discord economy bot.

```text
Discord command
    ↓
discord.py / py-cord / nextcord bot
    ↓ HTTPS, X-API-Key
Forge generated API
    ├─ auth / permission / rate-limit
    ├─ JSON Schema validation
    ├─ cache for reads
    ├─ named transactional RPC for money changes
    ├─ idempotency reservation
    └─ audit
    ↓
PostgreSQL / Supabase PostgreSQL
```

## The important rule: the bot does not run arbitrary SQL

Do **not** expose an endpoint like:

```json
{"sql":"UPDATE users SET balance = ..."}
```

A compromised bot/plugin key would become a database console.

Instead, SQL is server-owned inside app JSON. The caller sends only data to a named operation:

```http
POST /api/app1/v1/rpc/economy.transfer
X-API-Key: jf2_...
Idempotency-Key: discord:INTERACTION_ID
Content-Type: application/json

{"from_user":"111","to_user":"222","amount":25}
```

Forge selects the predeclared `economy.transfer` operation and binds those values to `:from_user`, `:to_user`, `:amount`.

## Step 1 — connect PostgreSQL

`app/App1/config/10-databases.json` chooses a server-side URL:

```json
{
  "databases": {
    "primary": {
      "url":"$env:APP1_DATABASE_URL",
      "pool_size":20,
      "max_overflow":40,
      "pool_timeout":10,
      "pool_pre_ping":true
    }
  }
}
```

`.env`:

```env
APP1_DATABASE_URL=postgresql+asyncpg://forge_user:PASSWORD@HOST:5432/economy
```

Only Forge needs this credential.

## Step 2 — declare account and ledger tables

The runnable example is `app/App1/config/70-economy-rpc.json`. It declares `economy_accounts` and read-only `economy_ledger` resources.

For a prototype, `auto_create:true` lets Forge create a declared table. For a mature production schema, use explicit migrations and set resources to reflect existing tables rather than relying on runtime schema creation.

Generated ordinary endpoints include:

```text
GET    /api/app1/v1/economy/accounts
GET    /api/app1/v1/economy/accounts/{id}
POST   /api/app1/v1/economy/accounts
PATCH  /api/app1/v1/economy/accounts/{id}
DELETE /api/app1/v1/economy/accounts/{id}
GET    /api/app1/v1/economy/ledger
```

Only actions present in `allowed_actions` are generated.

## Step 3 — create a narrow bot API key

Start the server with the bootstrap key in server environment, then provision a bot key:

```http
POST /api/app1/v1/admin/api-keys
X-API-Key: <BOOTSTRAP ADMIN KEY>
Content-Type: application/json

{
  "name":"discord-economy-production",
  "roles":["economy_bot"],
  "permissions":[],
  "rate_requests":600,
  "rate_window_seconds":60,
  "rate_burst":120
}
```

The raw generated key is returned when created. Store it as a bot/server secret. Forge stores its hash, not the original raw key.

Do not give the bot the bootstrap key.

## Step 4 — read data

A generic safe-filter example:

```http
GET /api/app1/v1/economy/accounts?balance__gte=1000&sort=-balance&limit=50
X-API-Key: jf2_...
```

Forge accepts only configured fields/operators. The client cannot submit a `WHERE` fragment.

For domain-oriented use, `economy.balance` is cleaner:

```http
GET /api/app1/v1/rpc/economy.balance/123456789
X-API-Key: jf2_...
```

Its JSON operation contains:

```json
{
  "sql":"SELECT discord_user_id, balance FROM economy_accounts WHERE discord_user_id = :user_id",
  "mode":"fetch_one",
  "params":{"user_id":"$path.user_id"}
}
```

## Step 5 — perform an atomic transfer

The transfer RPC performs debit, credit and ledger insert in one transaction. The debit SQL contains `balance >= :amount` and requires exactly one affected row.

That is safer than:

```text
SELECT balance
if enough:
  UPDATE ...
```

because two concurrent requests cannot both rely on the same stale pre-read.

The operation also has `idempotency:true`. Reuse the Discord interaction ID:

```python
await economy.transfer(
    str(interaction.user.id),
    str(member.id),
    amount,
    interaction_id=str(interaction.id),
)
```

See `examples/discord_economy/discord_py_example.py` and `bot_service.py`.

## Step 6 — grant/admin actions

`economy.grant` is intentionally separate from transfer. Give that permission only to trusted admin/internal service keys.

A third-party plugin might receive only:

```text
economy.balance.read
economy.ledger.read
```

and therefore cannot mint or transfer currency.

## How does a “SQL command” happen?

There are three levels:

**Resource CRUD** — no SQL in the app caller. Forge generates SQLAlchemy operations from resource JSON.

**Named RPC SQL** — server owner writes parameterized SQL in `operations[]`. The caller invokes the operation by HTTP. This is the recommended route for balances, purchases, inventory transactions, bank transfers and reports.

**Trusted Python hook** — use when the operation requires complex branches, Discord API checks, fraud rules, external SDKs or cryptographic verification. The hook can itself use application services/database code, but the public caller still invokes a fixed endpoint rather than submitting arbitrary code/SQL.

## Bot client SDK

`clients/python/json_api_forge_client.py` keeps one `httpx.AsyncClient` and therefore reuses HTTP connections. Example:

```python
from clients.python.json_api_forge_client import ForgeClient

api = ForgeClient("https://api.example.com/api/app1/v1", api_key)

balance = await api.request("GET", "/rpc/economy.balance/123")
transfer = await api.rpc(
    "economy.transfer",
    {"from_user":"123","to_user":"456","amount":50},
    idempotency_key="discord:987654321",
)
```

Close the client in your bot shutdown lifecycle.

## Production authorization warning

The demonstration RPC accepts `from_user` from the body because it illustrates the declarative SQL engine. In a real user-facing command, do not blindly trust a caller-supplied sender ID. Bind identity to the authenticated principal or verify Discord interaction/user ownership in a trusted hook/service. The database transaction protects money consistency; it does not decide who is morally/legally allowed to spend whose account.
