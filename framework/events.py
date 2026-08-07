from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncIterator

from fastapi import WebSocket


class EventHub:
    """In-process bounded pub/sub for a single worker."""
    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._websockets: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, event: Any) -> int:
        async with self._lock:
            queues = list(self._subscribers[channel]); sockets = list(self._websockets[channel])
        delivered = 0
        for queue in queues:
            try:
                queue.put_nowait(event); delivered += 1
            except asyncio.QueueFull:
                try:
                    queue.get_nowait(); queue.put_nowait(event); delivered += 1
                except (asyncio.QueueEmpty, asyncio.QueueFull): pass
        dead = []
        for ws in sockets:
            try: await ws.send_json(event); delivered += 1
            except Exception: dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead: self._websockets[channel].discard(ws)
        return delivered

    async def subscribe(self, channel: str, queue_size: int) -> AsyncIterator[Any]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        async with self._lock: self._subscribers[channel].add(queue)
        try:
            while True: yield await queue.get()
        finally:
            async with self._lock: self._subscribers[channel].discard(queue)

    async def connect_ws(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock: self._websockets[channel].add(websocket)

    async def disconnect_ws(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock: self._websockets[channel].discard(websocket)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class RedisEventHub(EventHub):
    """Redis pub/sub bridge so SSE/WebSocket events can cross workers and servers."""
    def __init__(self, url: str, prefix: str, project_slug: str):
        super().__init__()
        from redis.asyncio import from_url
        self.redis = from_url(url, encoding="utf-8", decode_responses=True)
        self.prefix = f"{prefix}:{project_slug}"
        self._listeners: dict[str, asyncio.Task] = {}
        self._listener_lock = asyncio.Lock()

    def _redis_channel(self, channel: str) -> str:
        return f"{self.prefix}:{channel}"

    async def _ensure_listener(self, channel: str) -> None:
        async with self._listener_lock:
            task = self._listeners.get(channel)
            if task and not task.done(): return
            self._listeners[channel] = asyncio.create_task(self._listen(channel), name=f"forge-redis-event-{channel}")

    async def _listen(self, channel: str) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self._redis_channel(channel))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message": continue
                try: event = json.loads(message["data"])
                except Exception: event = {"event": message["data"]}
                await super().publish(channel, event)
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(self._redis_channel(channel))
            await pubsub.aclose()

    async def publish(self, channel: str, event: Any) -> int:
        await self._ensure_listener(channel)
        return int(await self.redis.publish(self._redis_channel(channel), json.dumps(event, separators=(",", ":"), default=str)))

    async def subscribe(self, channel: str, queue_size: int) -> AsyncIterator[Any]:
        await self._ensure_listener(channel)
        async for event in super().subscribe(channel, queue_size):
            yield event

    async def connect_ws(self, channel: str, websocket: WebSocket) -> None:
        await self._ensure_listener(channel)
        await super().connect_ws(channel, websocket)

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def close(self) -> None:
        for task in self._listeners.values(): task.cancel()
        if self._listeners:
            await asyncio.gather(*self._listeners.values(), return_exceptions=True)
        await self.redis.aclose()


def build_event_hub(backend: str, redis_url: str | None, prefix: str, project_slug: str):
    if backend == "memory": return EventHub()
    if not redis_url: raise RuntimeError("realtime.backend='redis' requires REDIS_URL")
    return RedisEventHub(redis_url, prefix, project_slug)


def sse_encode(event: Any) -> bytes:
    return ("data: " + json.dumps(event, separators=(",", ":"), default=str) + "\n\n").encode("utf-8")
