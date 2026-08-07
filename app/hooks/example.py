async def ping_plugin(*, request, payload, principal, app):
    return {
        "pong": True,
        "caller": principal.subject,
        "payload": payload or {},
        "database_aliases": sorted(app.state.registry.engines.keys()),
    }
