# RealtimeSupport

Support-ticket CRUD paired with a bounded `ticket-updates` event channel over WebSocket and SSE. The channel has separate publish/subscribe permissions, explicit browser origins, queue/message limits and per-connection message rate limits.

After `forge init`, exchange `REALTIME_SUPPORT_BOOTSTRAP_ADMIN_KEY` for `support_agent` or `support_viewer` API keys. API prefix: `/api/realtime-support/v1`.
