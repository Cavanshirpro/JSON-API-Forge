# Row Ownership and Authorization

JSON API Forge v0.4 distinguishes **permission to use an endpoint** from **permission to act on a particular row**. A permission such as `social.posts.update` answers only the first question. It must not automatically imply that the caller may modify every post in the project.

This document defines the row-ownership model used by SQL and Mongo resources and explains where application-specific authorization still belongs in hooks or RPC operations.

## 1. The authorization layers

A protected resource can pass through several independent checks:

1. authentication — API key, JWT, or explicit public access;
2. permission/RBAC — may this principal call this action?;
3. tenant boundary — may this principal access this tenant?;
4. owner boundary — may this principal access this row?;
5. field policy — may this field be written/read?;
6. application invariant — is the action valid in the domain?

Do not collapse these layers into one broad role such as `social.*` unless that is genuinely intended.

## 2. SQL resource owner policy

A SQL resource can declare:

```json
{
  "table": "posts",
  "path": "social/posts",
  "owner_field": "author_id",
  "owner_actions": ["read", "update", "delete"],
  "owner_bypass_permission": "social.posts.moderate"
}
```

When an owner policy applies:

- create injects the authenticated principal identity into `owner_field`;
- the client cannot override that protected owner field;
- the configured actions add an owner predicate to the SQL query;
- an anonymous principal cannot satisfy an owner-bound private operation;
- a principal holding the explicit bypass permission can cross the owner boundary.

The principal identity for API keys is based on the immutable API-key database ID, not only on the display name. Two API keys with the same human-readable name therefore do not accidentally become the same owner.

## 3. Mongo resource owner policy

Mongo resources use the same concepts:

```json
{
  "database": "main",
  "collection": "profiles",
  "path": "profiles",
  "owner_field": "owner_id",
  "owner_actions": ["read", "update", "delete"],
  "owner_bypass_permission": "profiles.admin"
}
```

The owner predicate is composed with tenant and soft-delete predicates. Protected fields cannot be replaced through `PATCH` or `PUT`.

## 4. Tenant and owner are different

A tenant answers **which organization/server/workspace?**. Ownership answers **which principal owns the row?**.

Example:

```text
Tenant: discord-server-123
Owner:  api-key:84:economy-plugin
Row:    plugin-private-settings
```

A tenant administrator may need an owner-bypass permission, but a normal tenant member should not automatically receive it.

## 5. Protected policy fields

The framework treats these policy fields as server controlled when configured:

- `tenant_field`;
- `owner_field`;
- `soft_delete_field`.

They are not ordinary writable fields even when `writable_fields` is omitted. This prevents an update from moving a row to another tenant, transferring ownership, or resurrecting a soft-deleted row by directly editing policy metadata.

## 6. `owner_actions`

Ownership can be applied selectively. For example, a public profile may be readable by everyone but editable only by its owner:

```json
{
  "public_read": true,
  "owner_field": "owner_id",
  "owner_actions": ["update", "delete"]
}
```

Use the actual fields supported by the resource configuration; public endpoint behavior is still controlled by the resource permissions generated for the action. Ownership is an additional predicate, not a replacement for endpoint permissions.

## 7. Ownership is not relationship authorization

Owner policy deliberately remains simple. It does **not** implement:

- conversation membership;
- friends-only visibility;
- organization hierarchy;
- post audience rules;
- guild/channel permissions;
- game party membership;
- moderation precedence;
- ABAC expressions over arbitrary rows.

For those cases, use a permission plus a custom dependency/hook or a controlled RPC operation.

### Messaging example

A message row being owned by its sender is not enough to prove that another user may read the conversation. A complete messaging application must validate conversation membership before listing/reading messages. The built-in messaging pack supplies secure schema primitives, not a finished Discord authorization model.

### Gaming example

Ownership of an inventory row does not make the client authoritative over item quantity. Server-authoritative economy/inventory mutations should be RPC/hook operations that validate game rules.

## 8. Bypass permissions

A bypass permission must be explicit and narrow:

```json
"owner_bypass_permission": "social.posts.moderate"
```

Prefer this over a broad `*` role. A bypass permission is security-sensitive because it converts an owner-scoped query into a project/tenant-scoped query.

## 9. Cache isolation

Resource and operation cache keys include principal/owner context where required. A principal-dependent operation cannot safely disable principal variation if its SQL binds `$principal.*`; v0.4 rejects unsafe cache combinations during configuration validation.

## 10. Recommended policy checklist

For every mutable resource ask:

- Is the resource tenant scoped?
- Is it owner scoped?
- Which actions require ownership?
- Who may bypass ownership?
- Which fields are immutable/server controlled?
- Does a domain relationship need a hook instead of generic CRUD?
- Could a cache key erase an authorization dimension?

If any answer is unclear, do not expose broad generic write permissions.
