from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert

from .security import audit_table


class AuditWriter:
    """Bounded, batched audit writer so request latency is not tied to audit INSERT latency."""
    def __init__(self, engine, max_queue: int = 20_000, batch_size: int = 200, flush_interval: float = 0.25):
        self.engine = engine
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._task: asyncio.Task | None = None
        self.dropped = 0

    async def start(self):
        self._task = asyncio.create_task(self._run(), name="forge-audit-writer")

    def submit(self, **values):
        values["created_at"] = datetime.now(timezone.utc)
        try:
            self.queue.put_nowait(values)
        except asyncio.QueueFull:
            self.dropped += 1

    async def _run(self):
        while True:
            batch = []
            try:
                first = await self.queue.get()
                batch.append(first)
                deadline = asyncio.get_running_loop().time() + self.flush_interval
                while len(batch) < self.batch_size:
                    timeout = max(0.0, deadline - asyncio.get_running_loop().time())
                    if timeout == 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(self.queue.get(), timeout))
                    except asyncio.TimeoutError:
                        break
                async with self.engine.begin() as conn:
                    await conn.execute(insert(audit_table), batch)
                for _ in batch:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                for _ in batch:
                    self.queue.task_done()
                await asyncio.sleep(0.5)

    async def close(self):
        try:
            await asyncio.wait_for(self.queue.join(), timeout=3)
        except asyncio.TimeoutError:
            pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
