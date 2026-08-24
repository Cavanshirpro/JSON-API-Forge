from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ForgeError(RuntimeError):
    """Base exception raised by the JSON API Forge client."""


class ForgeTransportError(ForgeError):
    """The server could not be reached or timed out."""


class ForgeResponseTooLarge(ForgeError):
    """A response exceeded the configured safety limit."""


class ForgeClusterUnavailable(ForgeError):
    """No configured cluster endpoint could complete the request."""


class ForgeIntegrationError(ForgeError):
    """An optional integration is missing or returned an incompatible value."""


class ForgeSessionError(ForgeError):
    """The Editor control-plane session is missing or malformed."""


@dataclass(slots=True)
class ForgeHTTPError(ForgeError):
    status_code: int
    detail: Any
    request_id: str | None = None
    retry_after: str | None = None

    def __str__(self) -> str:
        suffix = f" request_id={self.request_id}" if self.request_id else ""
        return f"JSON API Forge returned HTTP {self.status_code}: {self.detail}{suffix}"
