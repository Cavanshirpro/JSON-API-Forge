# Messaging, social and gaming packs

Feature packs generate reusable data APIs so you do not repeatedly define common tables.

## Messaging

Generated resources: conversations, members, messages, reactions and receipts. Fields support message kinds, media IDs, reply references, edit/delete timestamps, mute state, last-read pointer and metadata.

Production messaging should additionally use a dedicated hook/service for: membership checks, block lists, spam controls, fan-out, push notifications and WebSocket delivery. The generic message table is storage infrastructure, not authorization logic.

## Social

Generated resources: profiles, posts, comments, reactions, follows and notifications. They cover common persistence primitives for feeds and community apps.

Feed ranking, visibility rules, private-account approval, moderation, mention processing and notification fan-out should be domain services. At large scale, maintain denormalized counters/feed indexes rather than counting reactions/follows on every request.

## Gaming

Generated resources: players, save slots, inventory, achievements, leaderboard rows and sessions.

Never let an untrusted game client directly write authoritative currency, inventory or leaderboard scores merely because CRUD exists. Expose server-validated hook endpoints. Competitive games normally need server authority, anti-replay/idempotency controls and anti-cheat telemetry.

## Why feature packs stay composable

Apps can enable one, all or none of these packs and can still add their own resource JSON fragments. Table prefixes avoid collisions with existing schemas.
