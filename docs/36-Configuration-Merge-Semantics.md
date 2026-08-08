# Configuration Merge Semantics

A project is assembled from `app.json` plus alphabetically sorted JSON fragments under `app/<Project>/config/`.

Merge behavior is deliberately **not** “append every array.” Security/policy lists need different semantics from declaration collections.

## 1. File order

Example:

```text
app/App1/app.json
app/App1/config/10-databases.json
app/App1/config/20-security.json
app/App1/config/40-resources.json
app/App1/config/80-data-events.json
```

Later fragments override earlier scalar/object values recursively.

## 2. Declaration collections append

These top-level declaration arrays append across fragments:

- `resources`;
- `mongo_resources`;
- `operations`;
- `data_sources`;
- `dependencies`;
- `custom_endpoints`;
- `event_channels`;
- `webhook_docs`.

This lets large applications split endpoints by domain.

## 3. Policy arrays replace

Other arrays are replaced by the later fragment. Examples include:

- CORS origins/methods/headers;
- trusted hosts;
- IP allow/deny lists;
- writable/readable fields;
- allowed filters/sorts;
- JWT algorithms;
- role permission arrays inside an overwritten object.

Why? If an operator writes a later fragment intending to narrow:

```json
"cors_origins": ["https://admin.example.com"]
```

retaining an older wildcard would be a dangerous surprise.

## 4. Clearing a policy

Because policy arrays replace, an empty array can intentionally clear an earlier policy list.

## 5. Object merge

Nested objects merge recursively by key until a scalar/list replacement rule applies. Avoid defining the same security setting in many fragments unless the precedence is intentional.

## 6. Unknown fields

All typed configuration models reject unknown fields. A misspelling is an error, not ignored metadata.

`$schema` is the explicit editor metadata exception and is stripped before runtime model validation.

## 7. Environment references

```json
"url": "$env:APP_DATABASE_URL"
```

is resolved from process environment first, then the deployment-root `.env` file. Do not commit real `.env` files.

## 8. Secret-safe validation errors

Resolved secret values are not included in formatted configuration-validation errors. The error reports the configuration location and message without echoing the secret-bearing input structure.

## 9. Recommended fragment ownership

A maintainable convention is:

```text
10-databases.json
20-security.json
30-performance.json
40-resources-*.json
50-features.json
60-custom-endpoints.json
70-rpc-*.json
80-data-events.json
```

The numbers are ordering tools, not mandatory semantic keywords.

## 10. Validate after every merge change

Run:

```bash
forge validate
forge doctor
forge schema
```

For deployment:

```bash
forge doctor --production
```

Do not infer final merged security policy by visually reading only one fragment.
