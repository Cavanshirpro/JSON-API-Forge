# TypeScript reference client

This directory is a **reference client**, not a separately distributed community package. It uses the platform `fetch()` API and is intended for browser, Node.js, Electron, plugin, and game-tooling integrations.

```ts
import { ForgeClient } from "./src/index.js";
const forge = new ForgeClient({ baseUrl: "https://api.example.com/api/app1/v1", apiKey: process.env.FORGE_API_KEY });
const balance = await forge.rpc("economy.balance", { user_id: "123" });
```

For a durable write, pass an application-level idempotency key. Keep API keys server-side whenever the client environment cannot protect secrets.
