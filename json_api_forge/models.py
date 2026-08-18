from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ForgeResponse(Generic[T]):
    data: T
    status_code: int
    request_id: str | None
    idempotent_replay: bool = False
    cache_status: str | None = None


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class RequestAttempt:
    method: str
    path: str
    attempt: int
    elapsed_seconds: float
    status_code: int | None
    request_id: str | None
    error: str | None
