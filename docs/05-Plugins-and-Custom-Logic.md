# Plugins and custom logic

The API-key system is designed for first-party and third-party plugins.

## Recommended plugin workflow

1. Define a role such as `calendar_plugin`.
2. Grant only required permissions.
3. Create one API key for one plugin installation/integration.
4. Plugin sends `X-API-Key` on every request.
5. Revoke only that key if compromised.

## Custom hook contract

Configured handler:

```json
"handler": "app.hooks.example:ping_plugin"
```

Function:

```python
async def ping_plugin(*, request, payload, principal, app):
    ...
```

Useful objects:

- `principal.subject`, `.roles`, `.permissions`
- `request.headers`, `.query_params`
- `payload`
- `app.state.registry.engines`
- `app.state.registry.tables`

## Keep hooks narrow

Treat hooks like stored procedures/business services, not as a second uncontrolled routing system. Put reusable infrastructure into `framework/`, and application-only rules into `app/hooks/`.
