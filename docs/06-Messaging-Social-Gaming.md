# Messaging, social and gaming feature packs

Feature packs generate **secure schema/resource primitives** so a project does not repeatedly define common tables. They are intentionally not complete products or domain-authorization engines.

## The rule to remember

```text
feature pack = persistence schema + generated API primitives
hook/RPC/policy = application-specific authority and invariants
```

A generated table being accessible through a permission does not prove that every caller holding that permission should see every row.

## Messaging

Generated resources include conversations, members, messages, reactions and receipts. Fields cover message kinds, media IDs, reply references, edit/delete timestamps, mute state, last-read pointers and metadata.

v0.4 hardens identity fields with owner policy where a simple owner relationship is valid. For example sender/user identity is server-injected rather than trusted from arbitrary client JSON.

However, a real messaging system still needs relationship authorization such as:

- is this principal a member of this conversation?;
- was the user removed/banned?;
- can this role post in this channel?;
- is this direct-message relationship blocked?;
- can a moderator cross an owner boundary?;
- how are attachments and mentions validated?;

Do **not** grant broad `messaging.messages.list/read` to untrusted clients and assume generic CRUD understands conversation membership. Put membership-aware reads/writes behind a dependency, hook or controlled RPC operation.

For high-volume messaging, durable fan-out/push/notification pipelines also belong outside the simple generated CRUD layer.

## Social

Generated resources include profiles, posts, comments, reactions, follows and notifications.

Identity fields such as `user_id`, `author_id` and `follower_id` are owner-bound where appropriate, so clients cannot simply submit another identity as the owner of a new row.

The pack still does not implement:

- private-account approval;
- block/mute graphs;
- post audience/visibility evaluation;
- follower-only feeds;
- moderation hierarchy;
- recommendation/feed ranking;
- abuse/spam policy;
- counter/materialized-feed maintenance.

Those rules are domain logic. Use the generated resources as the storage/API foundation, then expose the user-facing feed/actions through policy-aware hooks/RPC endpoints.

## Gaming

Generated resources include players, save slots, inventory, achievements, leaderboard rows and sessions.

v0.4 intentionally narrows the generic client write surface:

- player profile writes are limited to non-authoritative display data;
- save/inventory/achievement/leaderboard/session resources are generated read-oriented by default;
- currency, XP, inventory quantity, achievement progress and leaderboard score should be mutated only by trusted server logic.

A production game should use RPC/hooks for:

- reward validation;
- inventory transactions;
- economy settlement;
- save revision/checksum policy;
- leaderboard score verification;
- anti-replay/idempotency;
- anti-cheat/server authority;
- matchmaking/session invariants.

## Tenant scope

Each pack can declare a `tenant_field`. This is useful for server/guild/workspace separation, but tenant scope does not replace row ownership or relationship authorization.

## Permissions

Every generated resource receives action-specific permissions derived from its path. Avoid broad wildcards for untrusted clients. Give clients only the exact generated read/write actions that make sense, then add domain endpoints for the rest.

## Why packs remain optional

Apps can enable one, all or none of the packs and can still add ordinary JSON resources. Table prefixes avoid collisions with existing schemas.

The project will continue to prioritize the correctness of the shared runtime over adding larger “magic” feature packs that pretend to implement application business rules automatically.
