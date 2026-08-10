from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .cache import build_cache
from .config import ForgeConfig, ProjectConfig
from .datasources import DataSourceManager
from .db import build_registry
from .events import EventHub, build_event_hub
from .media import build_media_store
from .mongo import build_mongo_registry
from .protection import ConcurrencyGate
from .rate_limit import MemoryRateLimiter, RedisRateLimiter
from .settings import settings

log = logging.getLogger("json_api_forge.runtime")


@dataclass(slots=True)
class ProjectRuntime:
    config: ProjectConfig
    registry: Any = None
    mongo_registry: Any = None
    limiter: Any = None
    cache: Any = None
    gate: ConcurrencyGate | None = None
    media_store: Any = None
    data_sources: DataSourceManager | None = None
    event_hub: EventHub | None = None


class RuntimeManager:
    def __init__(self, forge: ForgeConfig):
        self.forge = forge
        self.runtimes = {project.slug: ProjectRuntime(config=project) for project in forge.projects}
        self._started = False

    def for_path(self, path: str) -> ProjectRuntime | None:
        matches = [runtime for runtime in self.runtimes.values() if path == runtime.config.api_prefix or path.startswith(runtime.config.api_prefix.rstrip("/") + "/")]
        return max(matches, key=lambda runtime: len(runtime.config.api_prefix or ""), default=None)

    def body_limit_for_path(self, path: str) -> int | None:
        runtime = self.for_path(path)
        return runtime.config.protection.max_request_body_bytes if runtime else None

    async def _start_runtime(self, runtime: ProjectRuntime) -> None:
        cfg = runtime.config
        runtime.registry = await build_registry(cfg)
        try:
            runtime.mongo_registry = await build_mongo_registry(cfg)
            if cfg.rate_limit.backend == "redis":
                if not settings.redis_url:
                    raise RuntimeError(f"Project {cfg.slug}: Redis rate limiter requires REDIS_URL")
                runtime.limiter = RedisRateLimiter(settings.redis_url, prefix=f"json-api-forge:rl:{cfg.slug}")
            else:
                runtime.limiter = MemoryRateLimiter(max_buckets=cfg.rate_limit.memory_max_buckets, idle_ttl_seconds=cfg.rate_limit.memory_idle_ttl_seconds, cleanup_interval_seconds=cfg.rate_limit.memory_cleanup_interval_seconds)
            runtime.cache = build_cache(cfg.cache, settings.redis_url)
            runtime.gate = ConcurrencyGate(cfg.protection.max_concurrent_requests, cfg.protection.max_queue_wait_seconds, cfg.protection.reject_when_saturated)
            runtime.data_sources = DataSourceManager(cfg)
            runtime.event_hub = build_event_hub(cfg.realtime.backend, settings.redis_url, cfg.realtime.redis_prefix, cfg.slug)
            if cfg.media.enabled:
                runtime.media_store = build_media_store(cfg.media)
        except Exception:
            await self._close_runtime(runtime, suppress=True)
            raise

    async def start(self) -> None:
        started: list[ProjectRuntime] = []
        try:
            for runtime in self.runtimes.values():
                await self._start_runtime(runtime)
                started.append(runtime)
                cfg = runtime.config
                log.info("Loaded project=%s resources=%d operations=%d data_sources=%d prefix=%s", cfg.slug, len(cfg.resources), len(cfg.operations), len(cfg.data_sources), cfg.api_prefix)
            self._started = True
        except Exception:
            for runtime in reversed(started):
                await self._close_runtime(runtime, suppress=True)
            raise

    async def _close_runtime(self, runtime: ProjectRuntime, *, suppress: bool) -> None:
        errors: list[Exception] = []
        for attr, close_name in (("event_hub", "close"), ("data_sources", "close"), ("cache", "close"), ("limiter", "close"), ("mongo_registry", "dispose"), ("registry", "dispose")):
            service = getattr(runtime, attr, None)
            if service is None: continue
            try:
                await getattr(service, close_name)()
            except Exception as exc:
                log.exception("Project cleanup failed project=%s service=%s", runtime.config.slug, attr)
                errors.append(exc)
            finally:
                setattr(runtime, attr, None)
        runtime.gate = None
        runtime.media_store = None
        if errors and not suppress:
            raise RuntimeError(f"Project {runtime.config.slug}: {len(errors)} cleanup operation(s) failed") from errors[0]

    async def close(self) -> None:
        errors: list[Exception] = []
        for runtime in reversed(list(self.runtimes.values())):
            try:
                await self._close_runtime(runtime, suppress=False)
            except Exception as exc:
                errors.append(exc)
        self._started = False
        if errors:
            raise RuntimeError(f"Runtime cleanup completed with {len(errors)} failure(s)") from errors[0]
