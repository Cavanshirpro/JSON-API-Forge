from __future__ import annotations

import asyncio
import ipaddress

from fastapi import HTTPException, Request


class ConcurrencyGate:
    def __init__(self, limit: int, wait_seconds: float, reject_when_saturated: bool = True):
        self.semaphore = asyncio.Semaphore(max(1, limit))
        self.wait_seconds = max(0.01, wait_seconds)
        self.reject = reject_when_saturated

    async def __aenter__(self):
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=self.wait_seconds)
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=503, detail="Server is temporarily saturated", headers={"Retry-After": "1"}) from exc
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.semaphore.release()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "0.0.0.0"


def ip_allowed(request: Request, allowed: list[str], denied: list[str]) -> bool:
    raw = client_ip(request)
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return not allowed

    for rule in denied:
        try:
            if ip in ipaddress.ip_network(rule, strict=False):
                return False
        except ValueError:
            if raw == rule:
                return False
    if not allowed:
        return True
    for rule in allowed:
        try:
            if ip in ipaddress.ip_network(rule, strict=False):
                return True
        except ValueError:
            if raw == rule:
                return True
    return False
